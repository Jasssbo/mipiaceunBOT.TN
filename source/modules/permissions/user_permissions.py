"""
Verifica dei permessi utente con cache multi-livello per evitare di sovraccaricare l'API Telegram.
Supporta sia verifica per user_id che per username, con fallback diretto su get_chat_member.
"""
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

_INACTIVE_STATUSES = {
    ChatMemberStatus.LEFT,
    ChatMemberStatus.BANNED,
    ChatMemberStatus.RESTRICTED,
}


async def _refresh_members_cache(client) -> None:
    """Aggiorna la cache dei membri del gruppo se scaduta."""
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
        logging.warning(f"[CACHE] Impossibile elencare l'intera lista membri ({e}); uso fallback get_chat_member.")


async def is_user_allowed_by_username(client, user) -> bool:
    """
    Verifica se l'utente è presente nel gruppo (tramite ID o username).
    Usa la cache locale e, se non trovato o a freddo, effettua una verifica puntuale con get_chat_member.
    """
    if not user:
        return False

    if user.id in ADMIN_IDS:
        return True

    try:
        await _refresh_members_cache(client)

        if user.id in _members_cache["user_ids"]:
            return True

        if user.username and user.username.lower() in _members_cache["usernames"]:
            return True

        # Fallback puntuale: utile per utenti appena entrati nel gruppo o se get_chat_members non è disponibile
        try:
            member = await client.get_chat_member(CHAT_ID, user.id)
            if member and member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                _members_cache["user_ids"].add(user.id)
                if user.username:
                    _members_cache["usernames"].add(user.username.lower())
                return True
        except Exception:
            pass

        return False
    except Exception:
        logging.exception("Errore durante il controllo della presenza dell'utente nel gruppo.")
        return False


def invalidate_members_cache() -> None:
    """Invalida la cache dei membri (utile dopo ban/unban)."""
    _members_cache["last_updated"] = 0.0
    _members_cache["usernames"].clear()
    _members_cache["user_ids"].clear()
