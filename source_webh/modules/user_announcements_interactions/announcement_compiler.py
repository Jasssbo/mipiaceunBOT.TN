"""
Compiler per preview e pubblicazione annunci (versione webhook).
Mantiene la stessa logica ma adatta per Redis state management.
"""
import logging
from config import CHAT_ID, GREEN, RED, YELLOW, RESET, POINTER_MESSAGE_IDS, get_user_data, set_user_data
from modules.topic_guardian import is_user_allowed_by_username
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pyrogram import errors
from pyrogram.types import InputMediaPhoto, InputMediaDocument

pointer_ids = POINTER_MESSAGE_IDS

# Funzione per cancellare i messaggi in modo sicuro, gestendo le eccezioni
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60),
       retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
async def safe_delete(client, chat_id, message_id):
    """
    Elimina i messaggi in modo sicuro, con tentativi multipli in caso di errori temporanei.
    In versione webhook: stessa logica, nessun cambiamento necessario.
    """
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass
    except Exception as e:
        logging.debug(f"[SAFE_DELETE] Errore eliminazione messaggio {message_id}: {e}")

# Funzione per costruire il testo dell'annuncio
def build_announcement_text(info, user, show_id=None):
    """
    Costruisce il testo dell'annuncio basato sui dati raccolti.
    In versione webhook: stessa logica, funzione pura (stateless).
    """
    cat = info["category"]
    if cat == "job":
        category_name = "Annuncio di Lavoro"
    elif cat == "project":
        category_name = "Progetto"
    elif cat == "event":
        category_name = "Evento"
    elif cat == "profile":
        category_name = "Profilo"
    else:
        category_name = cat.capitalize() if cat else ""
    
    author = f"@{user.username}" if user.username else user.first_name
    text = ""
    if show_id is not None:
        text += f"ID annuncio: {show_id}\n"
    text += f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
    
    for label, a in info["answers"].items():
        if a != "Saltato.":
            text += f"{label}\n{a}\n\n"
    
    return text

# --- Funzione per inviare la preview dell'annuncio in privato all'utente ---
async def send_preview(client, user_id, info):
    """
    Invia preview dell'annuncio all'utente in privato.
    In versione webhook: aggiorna Redis con preview_noid_msg_ids.
    """
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
    
    # Gestione multi-file
    files = info.get("files", {})
    multi_file_label = None
    multi_file_list = []
    for label, filelist in files.items():
        if filelist:
            multi_file_label = label
            multi_file_list = filelist
            break
    
    preview_noid_msg_ids = []
    
    if multi_file_list:
        # Media group (più file)
        media = []
        for idx, f in enumerate(multi_file_list):
            if f["file_type"] == "photo":
                media.append(InputMediaPhoto(f["file_id"], caption=text if idx == 0 else None))
            else:
                media.append(InputMediaDocument(f["file_id"], caption=text if idx == 0 else None))
        
        msgs = await client.send_media_group(user_id, media)
        preview_noid_msg_ids = [m.id for m in msgs]
        
        # Aggiorna info con ID messaggi preview (per cleanup successivo)
        info["preview_noid_msg_ids"] = preview_noid_msg_ids
        
        # Salva in Redis
        set_user_data(user_id, info)
        
        return msgs[0].id
    
    # File singolo o solo testo
    file_id = info.get("file")
    file_type = info.get("file_type")
    
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(user_id, file_id, caption=text)
        else:
            msg = await client.send_document(user_id, file_id, caption=text)
        preview_noid_msg_ids = [msg.id]
    else:
        msg = await client.send_message(user_id, text)
        preview_noid_msg_ids = [msg.id]
    
    # Aggiorna info e salva in Redis
    info["preview_noid_msg_ids"] = preview_noid_msg_ids
    set_user_data(user_id, info)
    
    return msg.id

# --- Funzione per aggiornare la preview dell'annuncio con l'ID assegnato dopo la pubblicazione ---
async def update_preview_with_id(client, user_id, preview_id, info, ann_id):
    """
    Aggiorna la preview con l'ID dell'annuncio dopo la pubblicazione.
    In versione webhook: stessa logica ma carica user info da Redis se necessario.
    """
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=ann_id)
    file_id = info.get("file")
    file_type = info.get("file_type")
    
    try:
        if file_id:
            await client.edit_message_caption(user_id, preview_id, caption=text)
        else:
            await client.edit_message_text(user_id, preview_id, text)
    except Exception as e:
        logging.warning(f"[PREVIEW] Impossibile aggiornare la preview con l'ID annuncio: {e}")

# --- Funzione per pubblicare l'annuncio nel topic corretto ---
async def publish_announcement(client, user_id, info, pointer_ids):
    """
    Pubblica l'annuncio nel gruppo nel topic corretto.
    In versione webhook: aggiorna Redis con last_ann_media_ids.
    """
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=None)
    
    # Gestione multi-file
    files = info.get("files", {})
    multi_file_label = None
    multi_file_list = []
    for label, filelist in files.items():
        if filelist:
            multi_file_label = label
            multi_file_list = filelist
            break
    
    pointer_id = pointer_ids.get(info["category"])
    username = user.username if user.username else user.first_name
    presente = await is_user_allowed_by_username(client, user)
    
    if not presente:
        logging.warning(f"[PUBLISH] Utente {username} non presente nel gruppo, pubblicazione annullata")
        return None
    
    msg = None
    ann_media_ids = []
    
    try:
        if multi_file_list:
            # Media group (più file)
            media = []
            for idx, f in enumerate(multi_file_list):
                if f["file_type"] == "photo":
                    media.append(InputMediaPhoto(f["file_id"], caption=text if idx == 0 else None))
                else:
                    media.append(InputMediaDocument(f["file_id"], caption=text if idx == 0 else None))
            
            msgs = await client.send_media_group(CHAT_ID, media, reply_to_message_id=pointer_id)
            if msgs:
                msg = msgs[0]
                ann_media_ids = [m.id for m in msgs]
        else:
            # File singolo o solo testo
            file_id = info.get("file")
            file_type = info.get("file_type")
            
            if file_id:
                if file_type == "photo":
                    msg = await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
                else:
                    msg = await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
            else:
                msg = await client.send_message(CHAT_ID, text, reply_to_message_id=pointer_id)
            
            if msg:
                ann_media_ids = [msg.id]
        
        # Salva ID messaggi pubblicati in Redis per cleanup futuro
        if ann_media_ids:
            info["last_ann_media_ids"] = ann_media_ids
            set_user_data(user_id, info)
        
        logging.info(f"[PUBLISH] Annuncio pubblicato da {username}, ID: {msg.id if msg else 'N/A'}")
        return msg
        
    except Exception as e:
        logging.exception(f"[PUBLISH] Errore nella pubblicazione per {username}: {e}")
        return None

# --- Funzione per inviare messaggi puliti (elimina precedenti) ---
async def send_clean_message(client, user_id, chat_id, text, reply_markup=None):
    """
    Invia un messaggio pulito, eliminando eventuali messaggi precedenti.
    In versione webhook: carica/salva da Redis i messaggi da eliminare.
    """
    # Carica user session da Redis per cleanup
    user_session = get_user_data(user_id)
    
    # Elimina messaggi precedenti se esistono
    if user_session and "messages_to_delete" in user_session:
        for mid in user_session["messages_to_delete"]:
            await safe_delete(client, user_id, mid)
        user_session["messages_to_delete"] = []
    
    # Invia nuovo messaggio
    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)
    
    # Salva ID per cleanup futuro
    if user_session:
        if "messages_to_delete" not in user_session:
            user_session["messages_to_delete"] = []
        user_session["messages_to_delete"].append(sent.id)
        user_session["last_bot_message_id"] = sent.id
        set_user_data(user_id, user_session)
    
    return sent