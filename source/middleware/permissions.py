import logging
from functools import wraps
from cachetools import TTLCache
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import GROUP_INVITE_LINK, ADMIN_IDS
from modules.permissions.user_permissions import check_user_access

# Cache checks per evitare chiamate inutili all'API Telegram (TTL: 5 minuti)
membership_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)
# Deduplicazione invio errore permessi (evita doppi messaggi tra handler su group=0 e group=1)
_recent_denials: TTLCache = TTLCache(maxsize=1000, ttl=3)


def build_access_denied_keyboard() -> InlineKeyboardMarkup:
    """Costruisce la tastiera inline con il link diretto al gruppo e il bottone di verifica immediata."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Entra nel Gruppo Community", url=GROUP_INVITE_LINK)],
        [InlineKeyboardButton("🔄 Sono entrato, verifica accesso", callback_data="verify_membership")],
    ])


def build_access_denied_text(user, is_member: bool, has_username: bool) -> str:
    """
    Costruisce un messaggio chiaro e professionale che blocca l'uso dei comandi
    ai non iscritti, fornisce il link diretto al gruppo e ricorda l'importanza del @username (Nick).
    """
    if not is_member and not has_username:
        return (
            "🔒 **Accesso riservato ai membri della Community**\n\n"
            "Ciao! Al momento non puoi inviare comandi al bot perché **non fai ancora parte del nostro gruppo** "
            "e **non hai un `@username` (Nick) impostato su Telegram**.\n\n"
            "⚠️ **Importante: imposta prima il tuo `@username` (Nick)!**\n"
            "Se non hai un Nick (`@username`) sul tuo profilo Telegram, **non puoi trovare il gruppo pubblico** "
            "tramite la ricerca, il bot non può verificarti e gli altri membri non potranno contattarti.\n"
            "• *Come fare:* vai nelle **Impostazioni di Telegram → Modifica profilo → Nome utente (Username)** e scegline uno.\n\n"
            f"📍 **Poi unisciti al gruppo cliccando qui:**\n👉 {GROUP_INVITE_LINK}\n\n"
            "Una volta impostato il Nick ed entrato nel gruppo, premi il bottone **\"🔄 Sono entrato, verifica accesso\"** qui sotto!"
        )

    if not is_member and has_username:
        uname = getattr(user, "username", "")
        return (
            "🔒 **Accesso riservato ai membri della Community**\n\n"
            "Ciao! Per poter usare il bot e i suoi comandi devi prima far parte del nostro gruppo Telegram.\n\n"
            f"📍 **Entra subito nel gruppo dal link ufficiale:**\n👉 {GROUP_INVITE_LINK}\n\n"
            "💡 **Promemoria sul Nick (`@username`):**\n"
            f"Ricorda di mantenere sempre attivo un `@username` pubblico nel profilo Telegram (il tuo attuale è `@{uname}` ✅): "
            "chi non ha un Nick impostato non riesce a trovare il gruppo pubblico e non può utilizzare il bot.\n\n"
            "Appena sei entrato nel gruppo, premi **\"🔄 Sono entrato, verifica accesso\"** qui sotto!"
        )

    # Caso: l'utente è già nel gruppo ma non ha un @username (Nick)
    return (
        "⚠️ **Manca il tuo `@username` (Nick) su Telegram!**\n\n"
        "Risulti già iscritto al gruppo della community ✅, ma il tuo account Telegram **non ha un `@username` pubblico impostato**.\n\n"
        "💡 **Perché serve il Nick (`@username`)?**\n"
        "Senza un `@username` pubblico non è possibile cercare i gruppi pubblici su Telegram, il bot non può associare il tuo profilo "
        "e gli altri professionisti non avrebbero modo di contattarti nei tuoi annunci.\n\n"
        "🛠️ **Come attivarlo in 10 secondi:**\n"
        "1. Apri le **Impostazioni di Telegram**\n"
        "2. Tocca **Modifica profilo → Nome utente (Username)**\n"
        "3. Scegli un nickname pubblico e salva.\n\n"
        "Appena fatto, premi **\"🔄 Sono entrato, verifica accesso\"** qui sotto!"
    )


def require_group_member(func):
    """
    Decoratore per verificare se l'utente è un membro del gruppo ed ha un @username attivo.
    Se non autorizzato, blocca qualsiasi comando/interazione e invia link del gruppo + reminder sul Nick.
    """
    @wraps(func)
    async def wrapper(client, update):
        user = getattr(update, "from_user", None)
        if not user:
            return

        user_id = user.id
        has_username = bool(getattr(user, "username", None)) or (user_id in ADMIN_IDS)
        is_verify_cb = isinstance(update, CallbackQuery) and getattr(update, "data", None) == "verify_membership"

        # Fast-path dalla cache solo se l'utente era già membro verificato, ha ancora l'username e non sta forzando il re-check
        if not is_verify_cb and has_username and membership_cache.get(user_id):
            return await func(client, update)

        is_member, has_username = await check_user_access(client, user, force_live=is_verify_cb)
        if is_member and has_username:
            membership_cache[user_id] = True
            return await func(client, update)

        membership_cache.pop(user_id, None)
        await send_permission_error(update, is_member=is_member, has_username=has_username)

    return wrapper


async def send_permission_error(update, is_member: bool = False, has_username: bool = False) -> None:
    """Invia il messaggio di blocco con il link al gruppo e il reminder sul @username (Nick)."""
    user = getattr(update, "from_user", None)
    user_id = user.id if user else 0

    try:
        if isinstance(update, Message):
            # Evita doppio invio quando lo stesso messaggio attraversa più handler (group=0 e group=1)
            dedup_key = f"msg:{user_id}:{update.id}"
            if dedup_key in _recent_denials:
                return
            _recent_denials[dedup_key] = True

            text = build_access_denied_text(user, is_member=is_member, has_username=has_username)
            await update.reply(
                text,
                reply_markup=build_access_denied_keyboard(),
                disable_web_page_preview=True,
            )
        elif isinstance(update, CallbackQuery):
            if not is_member and not has_username:
                alert_msg = (
                    "⚠️ Non risulti ancora nel gruppo e non hai un @username (Nick) impostato su Telegram!\n"
                    "Imposta un @username nelle Impostazioni di Telegram, entra nel gruppo dal bottone qui sopra e riprova."
                )
            elif not is_member:
                alert_msg = (
                    "⚠️ Non risulti ancora iscritto al gruppo!\n"
                    "Premi su '👥 Entra nel Gruppo Community', unisciti al gruppo e poi riprova."
                )
            else:
                alert_msg = (
                    "⚠️ Sei nel gruppo, ma non hai ancora impostato un @username (Nick) nelle Impostazioni di Telegram!\n"
                    "Impostalo nel tuo profilo Telegram e poi riprova."
                )
            await update.answer(alert_msg, show_alert=True)
    except Exception as e:
        logging.warning(f"Impossibile inviare errore di permessi: {e}")
