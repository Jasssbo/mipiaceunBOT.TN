"""
Utility generiche per la gestione dei messaggi.
"""
import logging
from typing import Optional, Union
from pyrogram.types import InlineKeyboardMarkup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pyrogram import errors
from config import RED, YELLOW, RESET

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60),
       retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
async def safe_delete(client, chat_id, message_id):
    """Elimina i messaggi in modo sicuro, con tentativi multipli in caso di errori temporanei."""
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass
    except Exception as e:
        logging.error(f"{RED}Errore nell'eliminazione del messaggio {message_id}: {str(e)}{RESET}")

async def send_clean_message(client, user_id: int, chat_id: int, text: str, 
                           reply_markup: Optional[InlineKeyboardMarkup] = None) -> Union[int, None]:
    """
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
    try:
        # Elimina i messaggi bot precedenti tracciati per questo utente (best-effort)
        try:
            from config import user_data as _user_data
            prev_bot_msgs = _user_data.get(user_id, {}).get('messages_to_delete', [])
            for mid in list(prev_bot_msgs):
                try:
                    await safe_delete(client, user_id, mid)
                except Exception:
                    pass
        except Exception:
            # Se non disponibile, prosegui comunque
            pass

        # Invia nuovo messaggio
        msg = await client.send_message(chat_id, text, reply_markup=reply_markup)

        # Assicuriamoci che user_data esista e aggiorniamo messages_to_delete
        try:
            from config import user_data as _user_data
            if user_id not in _user_data:
                _user_data[user_id] = {}
            if 'messages_to_delete' not in _user_data[user_id]:
                _user_data[user_id]['messages_to_delete'] = []
            _user_data[user_id]['messages_to_delete'].append(msg.id)
        except Exception:
            # Se non è possibile aggiornare lo stato, ignora ma restituisci comunque l'id
            pass

        return msg.id
    except Exception as e:
        logging.error(f"{YELLOW}Errore nell'invio del messaggio all'utente {user_id}: {str(e)}{RESET}")
        return None