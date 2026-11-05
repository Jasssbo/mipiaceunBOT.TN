"""
Verifica dei permessi utente con cache multi-livello per evitare di sovraccaricare l'API Telegram.
Supporta sia verifica per user_id che per username, con fallback diretto su get_chat_member.
"""
import asyncio
import logging
import time
from pyrogram.enums import ChatMemberStatus
from config import CHAT_ID, ADMIN_IDS

# --- Cache per i membri del gruppo ---
_members_cache = {
    "usernames": set(),
    "user_ids": set(),
    "last_updated": 0.0,
    "ttl_seconds": 300,  # Aggiorna ogni 5 minuti
}
_cache_refresh_lock = asyncio.Lock()

_INACTIVE_STATUSES = {
    ChatMemberStatus.LEFT,
    ChatMemberStatus.BANNED,
    ChatMemberStatus.RESTRICTED,
}


async def _refresh_members_cache(client) -> None:
    """Aggiorna la cache dei membri del gruppo se scaduta (protetta da lock contro stampede concorrenti)."""
    now = time.time()
    if now - _members_cache["last_updated"] < _members_cache["ttl_seconds"]:
        return

    async with _cache_refresh_lock:
        now = time.time()
        if now - _members_cache["last_updated"] < _members_cache["ttl_seconds"]:
            return

        try:
            usernames = set()
            user_ids = set()
            async for member in client.get_chat_members(CHAT_ID):
                if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                    continue
                if member.user:
                    user_ids.add(member.user.id)
                    if member.user.username:
                        usernames.add(member.user.username.lower())
            _members_cache["usernames"] = usernames
            _members_cache["user_ids"] = user_ids
            _members_cache["last_updated"] = now
            logging.debug(
                f"[CACHE] Aggiornata cache membri del gruppo: {len(user_ids)} utenti ({len(usernames)} con username)"
            )
        except Exception as e:
            # Evita retry tempesta ad ogni messaggio se get_chat_members fallisce temporaneamente
            _members_cache["last_updated"] = now - (_members_cache["ttl_seconds"] - 60)
            logging.warning(f"[CACHE] Impossibile elencare l'intera lista membri ({e}); uso fallback get_chat_member.")


async def check_user_access(client, user, force_live: bool = False) -> tuple[bool, bool]:
    """
    Verifica in modo granulare:
    1. Se l'utente è membro attivo del gruppo (`is_member`)
    2. Se l'utente ha un @username (Nick) pubblico impostato su Telegram (`has_username`)

    Returns:
        Tuple (is_member: bool, has_username: bool)
    """
    if not user:
        return False, False

    has_username = bool(getattr(user, "username", None))

    if user.id in ADMIN_IDS:
        return True, True

    try:
        if not force_live:
            await _refresh_members_cache(client)

            if user.id in _members_cache["user_ids"]:
                return True, has_username

            if has_username and user.username.lower() in _members_cache["usernames"]:
                return True, True

        # Verifica puntuale in tempo reale tramite API Telegram (fondamentale per chi è appena entrato nel gruppo)
        try:
            member = await client.get_chat_member(CHAT_ID, user.id)
            if member and member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                _members_cache["user_ids"].add(user.id)
                if member.user and member.user.username:
                    _members_cache["usernames"].add(member.user.username.lower())
                    has_username = True
                return True, has_username
        except Exception:
            pass

        return False, has_username
    except Exception:
        logging.exception("Errore durante il controllo della presenza dell'utente nel gruppo.")
        return False, has_username


async def is_user_allowed_by_username(client, user) -> bool:
    """
    Verifica se l'utente è presente nel gruppo ed ha i requisiti per interagire con il bot.
    """
    is_member, has_username = await check_user_access(client, user)
    return is_member and has_username


def invalidate_members_cache() -> None:
    """Invalida la cache dei membri (utile dopo ban/unban)."""
    _members_cache["last_updated"] = 0.0
    _members_cache["usernames"].clear()
    _members_cache["user_ids"].clear()
