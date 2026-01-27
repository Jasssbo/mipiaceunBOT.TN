"""
Handler per controllo e moderazione dei topic: elimina messaggi non consentiti nei topic vietati.
"""
import logging
from pyrogram import filters
from config import ALLOWED_TOPIC_IDS, NOT_ALLOWED_TOPIC_IDS, CHAT_ID, GREEN, RED, YELLOW, RESET, bot
from pyrogram.types import Message
from modules.permissions.user_permissions import is_user_allowed_by_username

@bot.on_message(filters.group)
async def topic_guardian_handler(client, message: Message):
    user = message.from_user
    if not user or not await is_user_allowed_by_username(client, user):
        logging.info(f"[TOPIC GUARDIAN] Utente non autorizzato/senza username/non preseente nel gruppo, messaggio ignorato.")
        return
    
    logging.info(f"[TOPIC GUARDIAN] Handler eseguito per message.id={getattr(message, 'id', None)} in chat.id={getattr(message.chat, 'id', None)}")
    if message.from_user and message.from_user.is_self:
        logging.info("[TOPIC GUARDIAN] Messaggio del bot, ignorato.")
        return

    topic_id = getattr(message, "message_thread_id", None)
    if topic_id is None and getattr(message, "reply_to_message_id", None):
        topic_id = getattr(message, "reply_to_message_id", None)
    if topic_id is None:
        try:
            if hasattr(client, "get_chat_message_link"):
                msg_link = await client.get_chat_message_link(message.chat.id, message.id)
                import re
                match = re.search(r"/([0-9]+)/([0-9]+)$", msg_link)
                if match:
                    topic_id = int(match.group(1))
                else:
                    match = re.search(r"/([0-9]+)$", msg_link)
                    if match:
                        topic_id = int(match.group(1))
        except Exception:
            pass

    logging.info(f"[TOPIC GUARDIAN] topic_id rilevato: {topic_id}")

    if topic_id is None:
        logging.info("[TOPIC GUARDIAN] Messaggio permesso: scritto nella chat generale (topic_id=None).")
        return
    if topic_id in NOT_ALLOWED_TOPIC_IDS:
        logging.info(f"[TOPIC GUARDIAN] Messaggio nel topic vietato: {topic_id}, eliminazione...")
        try:
            await client.delete_messages(message.chat.id, message.id)
            logging.info(f"[TOPIC GUARDIAN] Messaggio {message.id} eliminato dal topic vietato {topic_id}.")
        except Exception as e:
            logging.error(f"[TOPIC GUARDIAN] Errore eliminazione: {e}")
        return
    if topic_id in ALLOWED_TOPIC_IDS:
        logging.info(f"[TOPIC GUARDIAN] Messaggio permesso: scritto nel topic consentito ({topic_id}).")
        return
    logging.info(f"[TOPIC GUARDIAN] Messaggio in topic non gestito: {topic_id}, nessuna azione.")
    
