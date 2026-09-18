import logging
from functools import wraps
from cachetools import TTLCache
from pyrogram.types import Message, CallbackQuery

# Cache checks per evitare chiamate inutili all'API Telegram (TTL: 5 minuti)
membership_cache = TTLCache(maxsize=1000, ttl=300)

def require_group_member(func):
    """
    Decoratore per verificare se l'utente è un membro del gruppo.
    Restituisce un messaggio di errore se l'utente non è membro.
    """
    @wraps(func)
    async def wrapper(client, update):
        # Support both Message and CallbackQuery
        user = update.from_user
        if not user:
            return

        user_id = user.id
        
        # Check cache
        if user_id in membership_cache:
            if not membership_cache[user_id]:
                await send_permission_error(update)
                return
            return await func(client, update)
        
        # Check actual membership
        from modules.permissions.topic_permissions import is_user_allowed_by_username
        is_member = await is_user_allowed_by_username(client, user)
        
        membership_cache[user_id] = is_member
        
        if not is_member:
            await send_permission_error(update)
            return
            
        return await func(client, update)
        
    return wrapper

async def send_permission_error(update):
    """Utility per inviare l'errore di permessi"""
    msg = "❌ Mi dispiace, ma solo gli utenti presenti nel gruppo possono interagire con me."
    try:
        if isinstance(update, Message):
            await update.reply(msg)
        elif isinstance(update, CallbackQuery):
            await update.message.reply(msg)
    except Exception as e:
        logging.warning(f"Impossibile inviare errore di permessi: {e}")
