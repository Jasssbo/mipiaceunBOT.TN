"""
Gestione completa degli annunci: dalla raccolta dati alla pubblicazione.
"""
import logging
import asyncio
from typing import Optional, Dict, List, Union
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    Message,
    InputMediaPhoto,
    InputMediaDocument
)
from config import (
    GREEN, RED, YELLOW, RESET,
    CATEGORY_QUESTIONS, bot,
    CATEGORY_NAMES, announce_timeout,
    CHAT_ID, POINTER_MESSAGE_IDS
)
from .utils.message_utils import safe_delete, send_clean_message
from modules.permissions.topic_permissions import is_user_allowed_by_username
from core.session_manager import get_announcement_sessions
from services.message_service import get_message_service
from core.ui_components import build_main_menu_keyboard

# ------------------------ COSTANTI E CONFIGURAZIONE ------------------------
# Dizionario per tenere traccia dei messaggi di errore
error_messages: Dict[int, int] = {}

# Get service instances
sessions = get_announcement_sessions()
msg_service = get_message_service()

# ------------------------ FUNZIONI DI SUPPORTO ------------------------
def build_announcement_text(info: Dict, user, show_id: Optional[int] = None) -> str:
    """Costruisce il testo dell'annuncio basato sui dati raccolti."""
    cat = info["category"]
    category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
    
    author = f"@{user.username}" if user.username else user.first_name
    text = ""
    if show_id is not None:
        text += f"ID annuncio: {show_id}\n"
    text += f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
    
    for label, a in info["answers"].items():
        if a != "Saltato.":
            text += f"{label}\n{a}\n\n"
    return text

async def update_preview_with_id(client, user_id: int, preview_id: int, info: Dict, ann_id: int):
    """Aggiorna la preview dell'annuncio con l'ID assegnato dopo la pubblicazione."""
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=ann_id)
    
    try:
        if info.get("file"):
            await client.edit_message_caption(user_id, preview_id, caption=text)
        else:
            await client.edit_message_text(user_id, preview_id, text)
    except Exception as e:
        logging.warning(f"{YELLOW}Impossibile aggiornare la preview con l'ID annuncio: {str(e)}{RESET}")

async def add_file_and_confirm(client, user_id: int, info: Dict, label_text: str, file_id: str, file_type: str):
    """Aggiunge un file alla lista e invia conferma all'utente."""
    info["files"][label_text].append({"file_id": file_id, "file_type": file_type})
    sent = await client.send_message(
        user_id,
        f"✅ File aggiunto ({len(info['files'][label_text])}). Invia altri file o premi /done per continuare."
    )
    info["multi_file_temp_msgs"].append(sent.id)

# ------------------------ PREVIEW E PUBBLICAZIONE ------------------------
async def send_preview(client, user_id: int, info: Dict) -> int:
    """Invia la preview dell'annuncio all'utente."""
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
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
        media = []
        for idx, f in enumerate(multi_file_list):
            if f["file_type"] == "photo":
                media.append(InputMediaPhoto(f["file_id"], caption=text if idx == 0 else None))
            else:
                media.append(InputMediaDocument(f["file_id"], caption=text if idx == 0 else None))
        msgs = await client.send_media_group(user_id, media)
        preview_noid_msg_ids = [m.id for m in msgs]
        info["preview_noid_msg_ids"] = preview_noid_msg_ids
        return msgs[0].id
    
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
    
    info["preview_noid_msg_ids"] = preview_noid_msg_ids
    return msg.id

async def publish_announcement(client, user_id: int, info: Dict) -> Optional[Dict[str, any]]:
    """
    Pubblica l'annuncio nel topic corretto.
    
    Returns:
        Dict with 'message_id' (int) and 'media_ids' (list of ints for media groups)
    """
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=None)
    files = info.get("files", {})
    multi_file_label = None
    multi_file_list = []
    
    for label, filelist in files.items():
        if filelist:
            multi_file_label = label
            multi_file_list = filelist
            break

    try:
        category = info["category"]
        if category not in POINTER_MESSAGE_IDS:
            raise ValueError(f"Categoria non valida: {category}")
            
        thread_id = POINTER_MESSAGE_IDS[category]
        
        if multi_file_list:
            media = []
            for idx, f in enumerate(multi_file_list):
                if f["file_type"] == "photo":
                    media.append(InputMediaPhoto(f["file_id"], caption=text if idx == 0 else None))
                else:
                    media.append(InputMediaDocument(f["file_id"], caption=text if idx == 0 else None))
            msgs = await client.send_media_group(CHAT_ID, media, reply_to_message_id=thread_id)
            return {
                'message_id': msgs[0].id,
                'media_ids': [m.id for m in msgs]
            }
            
        file_id = info.get("file")
        file_type = info.get("file_type")
        if file_id:
            if file_type == "photo":
                msg = await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=thread_id)
            else:
                msg = await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=thread_id)
        else:
            msg = await client.send_message(CHAT_ID, text, reply_to_message_id=thread_id)
        
        return {
            'message_id': msg.id,
            'media_ids': [msg.id]
        }
    except Exception as e:
        logging.error(f"{RED}Errore durante la pubblicazione dell'annuncio: {str(e)}{RESET}")
        return None

# ------------------------ GESTIONE DATI UTENTE ------------------------
async def cleanup_user_data_and_messages(client, user_id: int, reason: str = "", cleanup_type: str = ""):
    """Pulisce i dati utente e i messaggi associati."""
    info = sessions.get_session(user_id)
    if not info:
        return

    try:
        user = await client.get_users(user_id)
        username = user.username if user.username else f"user{user.id}"
        category = info.get("category")
        if category:
            category_name = CATEGORY_NAMES.get(category, category.capitalize() if category else "")
            
            if cleanup_type == "timeout":
                logging.info(f"{YELLOW}[TIMEOUT ANNUNCIO] @{username} non ha completato la pubblicazione di un {category_name} entro il tempo limite{RESET}")
            elif cleanup_type == "cancel":
                logging.info(f"{YELLOW}[ANNUNCIO ANNULLATO] @{username} ha annullato la pubblicazione di un {category_name}{RESET}")
            else:
                logging.info(f"{YELLOW}[PUBBLICAZIONE INTERROTTA] @{username} ha interrotto la pubblicazione di un {category_name}{RESET}")
    except Exception as e:
        logging.error(f"{RED}Errore nel logging della cancellazione annuncio: {str(e)}{RESET}")

    # Cancella messaggi temporanei usando MessageService
    for mid in info.get("messages_to_delete", []):
        try:
            await msg_service.delete_message(client, user_id, mid)
        except Exception:
            pass
    
    for mid in info.get("multi_file_temp_msgs", []):
        try:
            await msg_service.delete_message(client, user_id, mid)
        except Exception:
            pass
    
    if user_id in error_messages:
        try:
            await msg_service.delete_message(client, user_id, error_messages[user_id])
            del error_messages[user_id]
        except Exception as e:
            logging.error(f"{RED}Errore nell'eliminazione del messaggio di errore durante il cleanup: {str(e)}{RESET}")
            del error_messages[user_id]

    for mid in info.get("user_messages_to_delete", []):
        try:
            await msg_service.delete_message(client, user_id, mid)
        except Exception:
            pass

    # Delete session using SessionManager
    sessions.delete_session(user_id)
    
    msg = "⏱️ Tempo scaduto, i dati inseriti sono stati eliminati. Sei tornato al Menù."
    if reason:
        msg = f"{reason}\n\n{msg}"
    
    # Send main menu using ui_components
    keyboard = build_main_menu_keyboard()
    await msg_service.send_message(client, user_id, msg, keyboard)

async def start_compilation_timeout(client, user_id: int, timeout: int):
    """Avvia il timer per il timeout della compilazione."""
    await asyncio.sleep(timeout)
    if sessions.has_session(user_id):
        await cleanup_user_data_and_messages(client, user_id, cleanup_type="timeout")

# ------------------------ HANDLER PRINCIPALE ------------------------
@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    """Handler principale per la raccolta dati utente."""
    user = message.from_user
    user_id = user.id
    
    # Gestisci solo utenti con sessione attiva e categoria impostata
    if not sessions.has_session(user_id):
        return
    
    info = sessions.get_session(user_id)
    if not info or not info.get("category"):
        return

    # Gestione messaggi di errore precedenti
    if user_id in error_messages:
        try:
            await msg_service.delete_message(client, user_id, error_messages[user_id])
            del error_messages[user_id]
        except Exception as e:
            logging.error(f"{RED}Errore nell'eliminazione del messaggio di errore: {str(e)}{RESET}")

    if "user_messages_to_delete" not in info:
        info["user_messages_to_delete"] = []
    info["user_messages_to_delete"].append(message.id)

    try:
        info = user_data[user_id]
        cat = info["category"]
        step = info["step"]

        # Log quando l'utente inizia una nuova pubblicazione
        if step == 0:
            category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
            username = user.username if user.username else f"user{user.id}"
            logging.info(f"{GREEN}[NUOVO ANNUNCIO] @{username} ha iniziato la pubblicazione di un {category_name}{RESET}")

        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]
        multi_file = question_data.get("multi_file", False)
        allowed_types = question_data.get("allowed_types", ["text"])

        # Inizializzazione files e multi_file_temp_msgs
        if multi_file:
            if "files" not in info:
                info["files"] = {}
            if label_text not in info["files"]:
                info["files"][label_text] = []
            if "multi_file_temp_msgs" not in info:
                info["multi_file_temp_msgs"] = []

        # Gestione domande multi-file
        if multi_file:
            if message.text and message.text.lower().strip() == "/done":
                # Elimina i messaggi di conferma temporanei
                for mid in info.get("multi_file_temp_msgs", []):
                    try:
                        await client.delete_messages(user.id, mid)
                        logging.debug(f"Eliminato messaggio conferma file ID: {mid}")
                    except Exception as e:
                        logging.error(f"{RED}Errore eliminazione conferma file: {str(e)}{RESET}")
                info["multi_file_temp_msgs"] = []
                
                if info["files"][label_text]:
                    info["answers"][label_text] = f"{len(info['files'][label_text])} file allegati."
                else:
                    info["answers"][label_text] = "Nessun file allegato."
                
                await proceed_to_next_step(client, user.id, info, cat)
                return

            # Gestione media group
            if getattr(message, "media_group_id", None) and message.photo:
                for photo in message.photo if isinstance(message.photo, list) else [message.photo]:
                    await add_file_and_confirm(client, user.id, info, label_text, photo.file_id, "photo")
                return

            if message.photo and not getattr(message, "media_group_id", None):
                await add_file_and_confirm(client, user.id, info, label_text, message.photo.file_id, "photo")
                return
            
            if message.document:
                await add_file_and_confirm(client, user.id, info, label_text, message.document.file_id, "document")
                return

            if message.text:
                error_msg = await client.send_message(user.id, "❗ Invia una foto o un documento, oppure premi /done per continuare.")
                error_messages[user_id] = error_msg.id
                return

            error_msg = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)} oppure /done.")
            error_messages[user_id] = error_msg.id
            return

        # Controllo tipo di messaggio
        msg_type = None
        username = user.username if user.username else f"user{user.id}"
        
        if message.text and not message.photo and not message.document:
            msg_type = "text"
        elif message.photo:
            msg_type = "photo"
            if "text" in allowed_types and not "photo" in allowed_types:
                logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato una foto quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.document:
            msg_type = "document"
            if "text" in allowed_types and not "document" in allowed_types:
                logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato un documento quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.audio:
            msg_type = "audio"
            if "text" in allowed_types and not "audio" in allowed_types:
                logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato un audio quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.voice:
            msg_type = "voice"
            if "text" in allowed_types and not "voice" in allowed_types:
                logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato una nota vocale quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.video:
            msg_type = "video"
            if "text" in allowed_types and not "video" in allowed_types:
                logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato un video quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.sticker:
            msg_type = "sticker"
            logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato uno sticker quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif message.animation:
            msg_type = "animation"
            logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato una GIF quando era richiesto del testo per la domanda '{label_text}'{RESET}")
        elif not msg_type:
            msg_type = "unknown"
            logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato un tipo di messaggio non supportato per la domanda '{label_text}'{RESET}")

        if msg_type and msg_type not in allowed_types:
            error_msg = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)}.")
            error_messages[user_id] = error_msg.id
            return

        # Gestione domande normali
        if message.photo or message.document:
            info["answers"][label_text] = "📎 File allegato."
            info["file"] = message.photo.file_id if message.photo else message.document.file_id
            info["file_type"] = "photo" if message.photo else "document"
        elif message.text:
            if "(opzionale)" in question_text.lower() and message.text.lower().strip() == "/skip":
                info["answers"][label_text] = "Saltato."
            else:
                info["answers"][label_text] = message.text.strip()

        await proceed_to_next_step(client, user.id, info, cat)

    except Exception as e:
        logging.exception(f"{YELLOW}Errore nella raccolta dei dati durante la compilazione dell'annuncio.{RESET}")
        await cleanup_user_data_and_messages(client, user.id, reason="❗ Si è verificato un errore durante la compilazione dell'annuncio.")

async def proceed_to_next_step(client, user_id: int, info: Dict, cat: str):
    """Procede al prossimo step della raccolta dati."""
    # Elimina l'ultima domanda del bot
    if info.get("messages_to_delete"):
        last_bot_msg = info["messages_to_delete"].pop()
        try:
            await msg_service.delete_message(client, user_id, last_bot_msg)
            logging.debug(f"Eliminata domanda bot ID: {last_bot_msg}")
        except Exception as e:
            logging.error(f"{RED}Errore nell'eliminazione della domanda del bot: {str(e)}{RESET}")
    
    # Elimina tutti i messaggi dell'utente (inclusi file/foto) uno per uno
    session = sessions.get_session(user_id)
    messages_to_clear = session.get("user_messages_to_delete", []) if session else []
    if messages_to_clear:
        logging.debug(f"Tentativo di eliminare {len(messages_to_clear)} messaggi utente")
        deleted_count = 0
        for mid in messages_to_clear:
            try:
                await msg_service.delete_message(client, user_id, mid)
                deleted_count += 1
                logging.debug(f"✓ Eliminato messaggio utente ID: {mid}")
            except Exception as e:
                logging.error(f"{RED}✗ Errore eliminazione messaggio {mid}: {str(e)}{RESET}")
        
        if deleted_count > 0:
            logging.info(f"{GREEN}Eliminati {deleted_count}/{len(messages_to_clear)} messaggi utente{RESET}")
    
    if session:
        session["user_messages_to_delete"] = []
    info["step"] += 1

    if info["step"] < len(CATEGORY_QUESTIONS[cat]):
        question_data = CATEGORY_QUESTIONS[cat][info["step"]]
        buttons = [[InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]]
        
        if question_data.get("skippable"):
            buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
        
        buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
        # Usa send_clean_message che elimina i messaggi bot precedenti e registra il nuovo
        sent_id = await send_clean_message(
            client,
            user_id,
            user_id,
            question_data["question"],
            InlineKeyboardMarkup(buttons)
        )
        # send_clean_message aggiorna info['messages_to_delete'] automaticamente
    else:
        # Tutte le domande completate - mostra preview e chiedi conferma
        preview_id = await send_preview(client, user_id, info)
        session = sessions.get_session(user_id)
        if session:
            session["preview_msg_id"] = preview_id
        
        confirm_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
            [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
            [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
        ])
            
        confirm_msg_id = await send_clean_message(client, user_id, user_id, "✅ Confermi di voler pubblicare questo annuncio?", confirm_btns)
        if session:
            session["confirm_msg_id"] = confirm_msg_id