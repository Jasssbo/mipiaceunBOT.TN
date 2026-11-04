"""
Handler per controllo e moderazione dei topic: elimina messaggi non consentiti nei topic vietati.
"""
import logging
import re
from pyrogram import filters
from pyrogram.types import Message
from config import ALLOWED_TOPIC_IDS, NOT_ALLOWED_TOPIC_IDS, CHAT_ID, ADMIN_IDS, bot
from modules.permissions.user_permissions import is_user_allowed_by_username


@bot.on_message(filters.group)
async def topic_guardian_handler(client, message: Message):
    if not message.chat or message.chat.id != CHAT_ID:
        return

    user = message.from_user
    if message.outgoing or (user and user.is_self):
        return

    # Gli amministratori configurati possono scrivere liberamente in qualsiasi topic
    if user and user.id in ADMIN_IDS:
        return

    topic_id = getattr(message, "message_thread_id", None)
    if topic_id is None and getattr(message, "reply_to_top_message_id", None):
        topic_id = getattr(message, "reply_to_top_message_id", None)
    if topic_id is None and getattr(message, "reply_to_message_id", None):
        topic_id = getattr(message, "reply_to_message_id", None)
    if topic_id is None:
        try:
            if hasattr(client, "get_chat_message_link"):
                msg_link = await client.get_chat_message_link(message.chat.id, message.id)
                match = re.search(r"/([0-9]+)/([0-9]+)$", msg_link)
                if match:
                    topic_id = int(match.group(1))
        except Exception:
            pass

    if topic_id is None:
        return

    if topic_id in NOT_ALLOWED_TOPIC_IDS:
        logging.info(
            f"[TOPIC GUARDIAN] Messaggio non autorizzato (msg_id={message.id}) nel topic riservato {topic_id}, eliminazione..."
        )
        try:
            await client.delete_messages(message.chat.id, message.id)
            logging.info(f"[TOPIC GUARDIAN] Messaggio {message.id} eliminato dal topic riservato {topic_id}.")
        except Exception as e:
            logging.error(f"[TOPIC GUARDIAN] Errore eliminazione messaggio {message.id}: {e}")
        return

    if topic_id in ALLOWED_TOPIC_IDS:
        return
