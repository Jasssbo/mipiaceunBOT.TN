"""
Verifica dei permessi utente con cache per evitare di sovraccaricare l'API Telegram.
"""
import logging
import time
from config import CHAT_ID

# --- Cache per i membri del gruppo ---
# Evita di chiamare get_chat_members ad ogni interazione (Telegram rate limiting)
_members_cache = {
    "usernames": set(),
    "last_updated": 0,
    "ttl_seconds": 300  # Aggiorna ogni 5 minuti
}


async def _refresh_members_cache(client):
    """Aggiorna la cache dei membri del gruppo se scaduta."""
    now = time.time()
    if now - _members_cache["last_updated"] < _members_cache["ttl_seconds"]:
        return  # Cache ancora valida

    try:
        usernames = set()
        async for member in client.get_chat_members(CHAT_ID):
            if member.user.username:
                usernames.add(member.user.username.lower())
        _members_cache["usernames"] = usernames
        _members_cache["last_updated"] = now
        logging.debug(f"[CACHE] Aggiornata cache membri del gruppo: {len(usernames)} utenti")
    except Exception as e:
        logging.error(f"[CACHE] Errore nell'aggiornamento della cache membri: {e}")
        # Se l'aggiornamento fallisce ma abbiamo dati vecchi, usiamoli
        if _members_cache["usernames"]:
            logging.warning("[CACHE] Usando cache scaduta per i membri del gruppo")
        else:
            raise


async def is_user_allowed_by_username(client, user):
    """
    Verifica se l'utente è presente nel gruppo tramite username.
    Usa una cache con TTL per evitare di chiamare get_chat_members ad ogni interazione.
    """
    try:
        await _refresh_members_cache(client)

        if not user.username:
            return False

        presente = user.username.lower() in _members_cache["usernames"]
        return presente
    except Exception as e:
        logging.exception(f"Errore durante il controllo dell'username nel gruppo.")
        return False


def invalidate_members_cache():
    """Invalida la cache dei membri (utile dopo ban/unban)."""
    _members_cache["last_updated"] = 0
