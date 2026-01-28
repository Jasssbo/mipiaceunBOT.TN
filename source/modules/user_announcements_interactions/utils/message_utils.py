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


async def send_clean_message(client, user_id: int, chat_id: int, text: str, 
                           reply_markup: Optional[InlineKeyboardMarkup] = None) -> Union[int, None]:
    """
    DEPRECATED: Use MessageService.send_and_track() instead.
    Invia un messaggio e gestisce eventuali errori.
    
    Args:
        client: Client Pyrogram
        user_id: ID dell'utente
        chat_id: ID della chat
        text: Testo del messaggio
        reply_markup: Markup opzionale per i bottoni

    Returns:
        ID del messaggio inviato o None in caso di errore
    """
    msg_service = get_message_service()
    
    try:
        from core.session_manager import get_announcement_sessions
        sessions = get_announcement_sessions()
        
        # Delete previously tracked messages for this user
        if sessions.has_session(user_id):
            session = sessions.get_session(user_id)
            prev_msgs = session.get('messages_to_delete', [])
            for mid in prev_msgs:
                try:
                    await msg_service.delete_message(client, user_id, mid)
                except Exception:
                    pass
            session['messages_to_delete'] = []
        
        # Send new message
        msg = await msg_service.send_message(client, chat_id, text, reply_markup)
        if msg and sessions.has_session(user_id):
            session = sessions.get_session(user_id)
            if 'messages_to_delete' not in session:
                session['messages_to_delete'] = []
            session['messages_to_delete'].append(msg.id)
        
        return msg.id if msg else None
            
    except Exception as e:
        logging.error(f"{YELLOW}Errore nell'invio del messaggio all'utente {user_id}: {str(e)}{RESET}")
        return None