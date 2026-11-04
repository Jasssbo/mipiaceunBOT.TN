"""
Utility generiche per la gestione dei messaggi.
DEPRECATED: Use services.message_service instead for new code.
"""
import logging
from typing import Optional, Union
from pyrogram.types import InlineKeyboardMarkup
from services.message_service import get_message_service
from config import RED, YELLOW, RESET


async def safe_delete(client, chat_id, message_id):
    """
    DEPRECATED: Use MessageService.delete_message() instead.
    Elimina i messaggi in modo sicuro, con tentativi multipli in caso di errori temporanei.
    """
    msg_service = get_message_service()
    try:
        await msg_service.delete_message(client, chat_id, message_id)
    except Exception as e:
        logging.error(f"{RED}Errore nell'eliminazione del messaggio {message_id}: {str(e)}{RESET}")


async def send_clean_message(
    client,
    user_id: int,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    session=None,
) -> Union[int, None]:
    """
    Invia un messaggio pulendo i messaggi precedenti del bot tracciati nella sessione.
    Ottimizzato per Upstash Redis: esegue al massimo 1 lettura (se `session` non è già fornita) e 1 sola scrittura finale.
    """
    msg_service = get_message_service()

    try:
        from core.session_manager import get_announcement_sessions
        sessions = get_announcement_sessions()

        if session is None:
            session = await sessions.get_session(user_id)

        # Delete previously tracked messages for this user
        if session is not None:
            prev_msgs = list(session.get("messages_to_delete", []))
            for mid in prev_msgs:
                try:
                    await msg_service.delete_message(client, user_id, mid)
                except Exception:
                    pass
            session["messages_to_delete"] = []

        # Send new message
        msg = await msg_service.send_message(client, chat_id, text, reply_markup)
        if session is not None:
            if msg:
                session["messages_to_delete"] = [msg.id]
            await sessions.save_session(session)

        return msg.id if msg else None

    except Exception as e:
        logging.error(f"{YELLOW}Errore nell'invio del messaggio all'utente {user_id}: {str(e)}{RESET}")
        return None