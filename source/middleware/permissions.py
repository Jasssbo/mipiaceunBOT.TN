import logging
from functools import wraps
from cachetools import TTLCache
from pyrogram.types import Message, CallbackQuery
from modules.permissions.user_permissions import is_user_allowed_by_username

# Cache checks per evitare chiamate inutili all'API Telegram (TTL: 5 minuti)
membership_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)


def require_group_member(func):
    """
    Decoratore per verificare se l'utente è un membro del gruppo.
    Restituisce un messaggio di errore se l'utente non è membro.
    """
    @wraps(func)
    async def wrapper(client, update):
        user = getattr(update, "from_user", None)
        if not user:
            return

        user_id = user.id

        # Check cache (solo i risultati positivi sono tenuti a lungo per permettere l'ingresso immediato a chi si unisce)
        if user_id in membership_cache and membership_cache[user_id]:
            return await func(client, update)

        is_member = await is_user_allowed_by_username(client, user)
        if is_member:
            membership_cache[user_id] = True
            return await func(client, update)

        await send_permission_error(update)

    return wrapper


async def send_permission_error(update) -> None:
    """Utility per inviare l'errore di permessi."""
    msg = "❌ Mi dispiace, ma solo gli utenti presenti nel gruppo possono interagire con me."
    try:
        if isinstance(update, Message):
            await update.reply(msg)
        elif isinstance(update, CallbackQuery):
            await update.answer(msg, show_alert=True)
    except Exception as e:
        logging.warning(f"Impossibile inviare errore di permessi: {e}")
