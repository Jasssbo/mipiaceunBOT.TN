import logging
from config import CHAT_ID, GREEN, RED, YELLOW, RESET, user_data, POINTER_MESSAGE_IDS
from modules.topic_guardian import is_user_allowed_by_username
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pyrogram import errors

pointer_ids = POINTER_MESSAGE_IDS

# Funzione per cancellare i messaggi in modo sicuro, gestendo le eccezioni
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60),
       retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
# safe_delete: Elimina i messaggi in modo sicuro, con tentativi multipli in caso di errori temporanei.
async def safe_delete(client, chat_id, message_id):
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass
    
# Funzione per costruire il testo dell'annuncio
def build_announcement_text(info, user, show_id=None):
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
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
    file_id = info.get("file")
    file_type = info.get("file_type")
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(user_id, file_id, caption=text)
        else:
            msg = await client.send_document(user_id, file_id, caption=text)
    else:
        msg = await client.send_message(user_id, text)
    return msg.id

# --- Funzione per aggiornare la preview dell'annuncio con l'ID assegnato dopo la pubblicazione ---
async def update_preview_with_id(client, user_id, preview_id, info, ann_id):
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
        logging.warning("Impossibile aggiornare la preview con l'ID annuncio.")

# --- Funzione per pubblicare l'annuncio nel topic corretto ---
async def publish_announcement(client, user_id, info, pointer_ids):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=None)
    file_id = info.get("file")
    file_type = info.get("file_type")
    pointer_id = pointer_ids.get(info["category"])
    username = user.username if user.username else user.first_name
    presente = await is_user_allowed_by_username(client, user)
    msg = None
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
        else:
            msg = await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
    else:
        msg = await client.send_message(CHAT_ID, text, reply_to_message_id=pointer_id)
    ann_id = msg.id if msg else None
    if presente is True:
        logging.info(f"{GREEN}[PUBBLICAZIONE] l'Utente: {username} ha pubblicato un annuncio, ID annuncio: {ann_id}. L'Utente è Presente nel gruppo.{RESET}")
    elif presente is False:
        logging.info(f"{RED}[PUBBLICAZIONE ERRATA] l'Utente: {username} ha provato a pubblicare un annuncio con ID {ann_id}, ma NON è Presente nel gruppo. {RESET}")
    elif presente is None:
        logging.info(f"{YELLOW}[ERRORE IN FASE DI PUBBLICAZIONE] l'Utente: {username} ha provato a pubblicare un annuncio ID {ann_id}, ma NON è stato riconosciuto il suo username. {RESET}")
    else:
        logging.info(f"{YELLOW}[ERRORE SCONOSCIUTO] l'Utente: {username} ha provato a pubblicare un annuncio ID {ann_id}, ma si è verificato un errore imprevisto. {RESET}")
    return msg

# --- Funzione per cancellare i messaggi precedenti dell'utente e inviare un nuovo messaggio pulito
# Aggiorna lo stato utente per tracciare l'ultimo messaggio inviato e quelli da eliminare. ---
async def send_clean_message(client, user_id, chat_id, text, reply_markup=None):
    for mid in user_data.get(user_id, {}).get("messages_to_delete", []):
        try:
            await client.delete_messages(chat_id, mid)
        except Exception:
            pass
    if user_id in user_data:
        user_data[user_id]["messages_to_delete"] = []
    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)
    if user_id not in user_data:
        user_data[user_id] = {"last_bot_message_id": None, "messages_to_delete": []}
    user_data[user_id]["last_bot_message_id"] = sent.id
    user_data[user_id]["messages_to_delete"].append(sent.id)
