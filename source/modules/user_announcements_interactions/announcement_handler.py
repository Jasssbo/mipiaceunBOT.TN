"""
Gestione completa degli annunci: dalla raccolta dati alla pubblicazione.
"""
import logging
import asyncio
import re
from typing import Optional, Dict, List, Union
from cachetools import TTLCache
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    Message,
    InputMediaPhoto,
    InputMediaDocument
)
from config import (
    CATEGORY_QUESTIONS, bot,
    CATEGORY_NAMES, announce_timeout,
    CHAT_ID, POINTER_MESSAGE_IDS,
    MAX_INPUT_LENGTH, MAX_ANNOUNCEMENTS_PER_DAY,
    RED, GREEN, YELLOW, BLUE, RESET
)
from .utils.message_utils import safe_delete, send_clean_message
from modules.permissions.user_permissions import is_user_allowed_by_username
from middleware.permissions import require_group_member
from core.session_manager import get_announcement_sessions
from services.message_service import get_message_service
from core.ui_components import build_main_menu_keyboard

# Get service instances
sessions = get_announcement_sessions()
msg_service = get_message_service()

# Limite massimo Telegram per send_media_group (2..10 elementi)
MAX_FILES_PER_ANNOUNCEMENT = 10

# Per-user lock con TTL per prevenire race condition nell'invio di album senza memory leak (OWASP A10)
_user_locks: TTLCache = TTLCache(maxsize=2000, ttl=1800)
# Task di timeout attivi per utente (evita che vecchi timer scadano su nuove sessioni)
_timeout_tasks: Dict[int, asyncio.Task] = {}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _sanitize_log(value: str, max_len: int = 80) -> str:
    """Rimuove caratteri di controllo, newline e sequenze ANSI per prevenire Log Injection (OWASP A09)."""
    cleaned = _CONTROL_CHARS_RE.sub(" ", str(value or "")).strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned


def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


def cancel_compilation_timeout(user_id: int) -> None:
    """Annulla il timer di timeout attivo per l'utente, se presente."""
    task = _timeout_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()


async def reschedule_compilation_timeout(
    client,
    user_id: int,
    timeout: int = announce_timeout,
    sync_redis_ttl: bool = True,
) -> None:
    """Avvia o riavvia il timer di inattività (10 minuti) per la compilazione dell'annuncio."""
    cancel_compilation_timeout(user_id)
    if sync_redis_ttl:
        # Imposta il TTL su Redis con un margine di +30s così il task invia l'avviso e pulisce i messaggi prima dell'eviction
        await sessions.schedule_cleanup(user_id, timeout + 30)
    _timeout_tasks[user_id] = asyncio.create_task(
        start_compilation_timeout(client, user_id, timeout)
    )

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
    caption_text = text[:1020] + "…" if len(text) > 1024 else text
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
        if len(multi_file_list) == 1:
            f = multi_file_list[0]
            if f["file_type"] == "photo":
                msg = await client.send_photo(user_id, f["file_id"], caption=caption_text)
            else:
                msg = await client.send_document(user_id, f["file_id"], caption=caption_text)
            preview_noid_msg_ids = [msg.id]
            info["preview_noid_msg_ids"] = preview_noid_msg_ids
            return msg.id

        media = []
        for idx, f in enumerate(multi_file_list[:MAX_FILES_PER_ANNOUNCEMENT]):
            if f["file_type"] == "photo":
                media.append(InputMediaPhoto(f["file_id"], caption=caption_text if idx == 0 else None))
            else:
                media.append(InputMediaDocument(f["file_id"], caption=caption_text if idx == 0 else None))
        msgs = await client.send_media_group(user_id, media)
        preview_noid_msg_ids = [m.id for m in msgs]
        info["preview_noid_msg_ids"] = preview_noid_msg_ids
        return msgs[0].id
    
    file_id = info.get("file")
    file_type = info.get("file_type")
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(user_id, file_id, caption=caption_text)
        else:
            msg = await client.send_document(user_id, file_id, caption=caption_text)
        preview_noid_msg_ids = [msg.id]
    else:
        msg = await client.send_message(user_id, text[:4096])
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
    caption_text = text[:1020] + "…" if len(text) > 1024 else text
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
            if len(multi_file_list) == 1:
                f = multi_file_list[0]
                if f["file_type"] == "photo":
                    msg = await client.send_photo(CHAT_ID, f["file_id"], caption=caption_text, reply_to_message_id=thread_id)
                else:
                    msg = await client.send_document(CHAT_ID, f["file_id"], caption=caption_text, reply_to_message_id=thread_id)
                return {
                    'message_id': msg.id,
                    'media_ids': [msg.id]
                }

            media = []
            for idx, f in enumerate(multi_file_list[:MAX_FILES_PER_ANNOUNCEMENT]):
                if f["file_type"] == "photo":
                    media.append(InputMediaPhoto(f["file_id"], caption=caption_text if idx == 0 else None))
                else:
                    media.append(InputMediaDocument(f["file_id"], caption=caption_text if idx == 0 else None))
            msgs = await client.send_media_group(CHAT_ID, media, reply_to_message_id=thread_id)
            return {
                'message_id': msgs[0].id,
                'media_ids': [m.id for m in msgs]
            }
            
        file_id = info.get("file")
        file_type = info.get("file_type")
        if file_id:
            if file_type == "photo":
                msg = await client.send_photo(CHAT_ID, file_id, caption=caption_text, reply_to_message_id=thread_id)
            else:
                msg = await client.send_document(CHAT_ID, file_id, caption=caption_text, reply_to_message_id=thread_id)
        else:
            msg = await client.send_message(CHAT_ID, text[:4096], reply_to_message_id=thread_id)
        
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
    cancel_compilation_timeout(user_id)
    info = await sessions.get_session(user_id)
    if not info:
        return

    try:
        user = await client.get_users(user_id)
        username = _sanitize_log(user.username if user.username else f"user{user.id}", max_len=40)
        category = info.get("category")
        if category:
            category_name = CATEGORY_NAMES.get(category, category.capitalize() if category else "")
            
            if cleanup_type == "timeout":
                logging.info(f"{YELLOW}[TIMEOUT ANNUNCIO] @{username} non ha completato la pubblicazione di '{category_name}' entro i 10 minuti{RESET}")
            elif cleanup_type == "cancel":
                logging.info(f"{YELLOW}[ANNUNCIO ANNULLATO] @{username} ha annullato la pubblicazione di '{category_name}'{RESET}")
            else:
                logging.info(f"{YELLOW}[PUBBLICAZIONE INTERROTTA] @{username} ha interrotto la pubblicazione di '{category_name}'{RESET}")
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
    
    err_msg_id = info.get("error_msg_id")
    if err_msg_id:
        try:
            await msg_service.delete_message(client, user_id, err_msg_id)
        except Exception as e:
            logging.error(f"{RED}Errore nell'eliminazione del messaggio di errore durante il cleanup: {str(e)}{RESET}")

    for mid in info.get("user_messages_to_delete", []):
        try:
            await msg_service.delete_message(client, user_id, mid)
        except Exception:
            pass

    # Delete session using SessionManager (1 solo comando DEL su Redis)
    await sessions.delete_session(user_id)
    
    # Se è un annullamento esplicito, il messaggio del menu viene già inviato da buttons.py
    if cleanup_type == "cancel":
        return

    msg = "⏱️ Tempo scaduto (10 minuti di inattività), i dati inseriti sono stati eliminati. Sei tornato al Menù."
    if reason:
        msg = f"{reason}\n\nSei tornato al Menù."
    
    # Send main menu using ui_components
    keyboard = build_main_menu_keyboard()
    await msg_service.send_message(client, user_id, msg, keyboard)

async def start_compilation_timeout(client, user_id: int, timeout: int):
    """Avvia il timer per il timeout della compilazione e rilascia sempre il riferimento al task in memoria."""
    try:
        await asyncio.sleep(timeout)
        info = await sessions.get_session(user_id)
        # Verifica che ci sia effettivamente una compilazione attiva (category != None)
        if info and info.get("category"):
            await cleanup_user_data_and_messages(client, user_id, cleanup_type="timeout")
    except asyncio.CancelledError:
        pass
    finally:
        if _timeout_tasks.get(user_id) is asyncio.current_task():
            _timeout_tasks.pop(user_id, None)

# ------------------------ HANDLER PRINCIPALE ------------------------
@bot.on_message(filters.private & ~filters.command(["start", "privacy", "informativa", "informativa_privacy", "terms", "termini", "tos", "my_data", "miei_dati", "erase_my_data", "erase", "gdpr_erase", "admin_reports", "admin_segnalazioni", "admin_ban", "admin_unban", "admin_clear_reports"]))
@require_group_member
async def collect_data_handler(client, message: Message):
    """Handler principale per la raccolta dati utente (ottimizzato a 1 GET + 1 SET su Upstash Redis per step)."""
    user = message.from_user
    if not user:
        return
    user_id = user.id
    username = _sanitize_log(user.username if user.username else f"user{user_id}", max_len=40)
    session_ttl = announce_timeout + 30

    async with _get_user_lock(user_id):
        # 1 sola lettura Redis (GET) per verificare e caricare la sessione
        info = await sessions.get_session(user_id)
        if not info or not info.get("category"):
            return

        # Rinnova il task di timeout in-memory (il TTL Redis viene rinnovato atomicamente nel save_session finale)
        await reschedule_compilation_timeout(client, user_id, announce_timeout, sync_redis_ttl=False)

        # Gestione messaggi di errore precedenti salvati direttamente in UserSession (0 comandi Redis extra)
        err_msg_id = info.get("error_msg_id")
        if err_msg_id:
            try:
                await msg_service.delete_message(client, user_id, err_msg_id)
            except Exception as e:
                logging.error(f"{RED}Errore nell'eliminazione del messaggio di errore: {str(e)}{RESET}")
            info["error_msg_id"] = None

        if "user_messages_to_delete" not in info:
            info["user_messages_to_delete"] = []
        info["user_messages_to_delete"].append(message.id)

        try:
            cat = info["category"]
            step = info["step"]
            total_steps = len(CATEGORY_QUESTIONS[cat])
            category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")

            question_data = CATEGORY_QUESTIONS[cat][step]
            question_text = question_data["question"]
            label_text = question_data["label"]
            multi_file = question_data.get("multi_file", False)
            allowed_types = question_data.get("allowed_types", ["text"])

            # Inizializzazione files e multi_file_temp_msgs in memoria
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
                    
                    num_files = len(info["files"][label_text])
                    if num_files > 0:
                        info["answers"][label_text] = f"{num_files} file allegati."
                    else:
                        info["answers"][label_text] = "Nessun file allegato."
                    
                    logging.info(
                        f"{GREEN}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha completato '{label_text}' -> {info['answers'][label_text]}{RESET}"
                    )
                    await proceed_to_next_step(client, user.id, info, cat)
                    return

                # Verifica limite massimo di file per annuncio (10 per media_group Telegram)
                if (message.photo or message.document) and len(info["files"][label_text]) >= MAX_FILES_PER_ANNOUNCEMENT:
                    error_msg = await client.send_message(
                        user.id,
                        f"⚠️ Hai raggiunto il limite massimo di {MAX_FILES_PER_ANNOUNCEMENT} file per annuncio. Premi /done per continuare.",
                    )
                    info["error_msg_id"] = error_msg.id
                    await sessions.save_session(info, expire=session_ttl)
                    return

                # Gestione media group
                if getattr(message, "media_group_id", None) and message.photo:
                    for photo in message.photo if isinstance(message.photo, list) else [message.photo]:
                        if len(info["files"][label_text]) < MAX_FILES_PER_ANNOUNCEMENT:
                            await add_file_and_confirm(client, user.id, info, label_text, photo.file_id, "photo")
                    logging.info(
                        f"{BLUE}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha caricato foto per '{label_text}' (totale: {len(info['files'][label_text])}){RESET}"
                    )
                    await sessions.save_session(info, expire=session_ttl)
                    return

                if message.photo and not getattr(message, "media_group_id", None):
                    await add_file_and_confirm(client, user.id, info, label_text, message.photo.file_id, "photo")
                    logging.info(
                        f"{BLUE}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha caricato una foto per '{label_text}' (totale: {len(info['files'][label_text])}){RESET}"
                    )
                    await sessions.save_session(info, expire=session_ttl)
                    return
                
                if message.document:
                    await add_file_and_confirm(client, user.id, info, label_text, message.document.file_id, "document")
                    logging.info(
                        f"{BLUE}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha caricato un documento per '{label_text}' (totale: {len(info['files'][label_text])}){RESET}"
                    )
                    await sessions.save_session(info, expire=session_ttl)
                    return

                if message.text:
                    error_msg = await client.send_message(user.id, "❗ Invia una foto o un documento, oppure premi /done per continuare.")
                    info["error_msg_id"] = error_msg.id
                    await sessions.save_session(info, expire=session_ttl)
                    return

                error_msg = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)} oppure /done.")
                info["error_msg_id"] = error_msg.id
                await sessions.save_session(info, expire=session_ttl)
                return

            from services.validation_service import create_validator_from_question
            validator = create_validator_from_question(question_data)
            is_valid, error = await validator.validate(message)
            
            if not is_valid:
                error_msg = await client.send_message(user.id, error)
                info["error_msg_id"] = error_msg.id
                await sessions.save_session(info, expire=session_ttl)
                return

            # Gestione domande normali
            if message.photo or message.document:
                info["answers"][label_text] = "📎 File allegato."
                info["file"] = message.photo.file_id if message.photo else message.document.file_id
                info["file_type"] = "photo" if message.photo else "document"
                logging.info(
                    f"{GREEN}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                    f"ha allegato {info['file_type']} per '{label_text}'{RESET}"
                )
            elif message.text:
                if "(opzionale)" in question_text.lower() and message.text.lower().strip() == "/skip":
                    info["answers"][label_text] = "Saltato."
                    logging.info(
                        f"{YELLOW}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha saltato '{label_text}'{RESET}"
                    )
                else:
                    clean_text = message.text.strip()
                    info["answers"][label_text] = clean_text
                    preview_val = _sanitize_log(clean_text, max_len=80)
                    logging.info(
                        f"{GREEN}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                        f"ha inserito '{label_text}' -> \"{preview_val}\"{RESET}"
                    )

            await proceed_to_next_step(client, user.id, info, cat)

        except Exception as e:
            logging.exception(f"Errore nella raccolta dei dati durante la compilazione dell'annuncio.")
            await cleanup_user_data_and_messages(client, user.id, reason="❗ Si è verificato un errore durante la compilazione dell'annuncio.")

async def proceed_to_next_step(client, user_id: int, info: Dict, cat: str):
    """Procede al prossimo step della raccolta dati con 1 sola scrittura finale su Redis."""
    session_ttl = announce_timeout + 30
    # Elimina l'ultima domanda del bot
    if info.get("messages_to_delete"):
        last_bot_msg = info["messages_to_delete"].pop()
        try:
            await msg_service.delete_message(client, user_id, last_bot_msg)
            logging.debug(f"Eliminata domanda bot ID: {last_bot_msg}")
        except Exception as e:
            logging.error(f"{RED}Errore nell'eliminazione della domanda del bot: {str(e)}{RESET}")
    
    # Elimina i messaggi dell'utente inviati in questo step e svuota la lista in `info`
    messages_to_clear = list(info.get("user_messages_to_delete", []))
    if messages_to_clear:
        deleted_count = 0
        for mid in messages_to_clear:
            try:
                await msg_service.delete_message(client, user_id, mid)
                deleted_count += 1
            except Exception as e:
                logging.debug(f"Impossibile eliminare messaggio {mid}: {str(e)}")
        logging.debug(f"Pulizia chat privata: eliminati {deleted_count}/{len(messages_to_clear)} messaggi utente")
    
    info["user_messages_to_delete"] = []
    info["step"] += 1

    if info["step"] < len(CATEGORY_QUESTIONS[cat]):
        question_data = CATEGORY_QUESTIONS[cat][info["step"]]
        buttons = [[InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]]
        
        if question_data.get("skippable"):
            buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
        
        buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
        # Passa `session=info` a send_clean_message così esegue 0 GET e 1 solo SET finale
        await send_clean_message(
            client,
            user_id,
            user_id,
            question_data["question"],
            InlineKeyboardMarkup(buttons),
            session=info,
        )
    else:
        # Tutte le domande completate - mostra preview e chiedi conferma
        category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
        logging.info(f"{BLUE}[ANTEPRIMA {category_name}] user_id={user_id} ha completato tutte le domande, invio anteprima di conferma{RESET}")
        preview_id = await send_preview(client, user_id, info)
        info["preview_msg_id"] = preview_id
        
        confirm_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
            [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
            [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
        ])
            
        confirm_msg = await msg_service.send_message(client, user_id, "✅ Confermi di voler pubblicare questo annuncio?", confirm_btns)
        if confirm_msg:
            info["confirm_msg_id"] = confirm_msg.id
            info["messages_to_delete"] = [confirm_msg.id]
        await sessions.save_session(info, expire=session_ttl)