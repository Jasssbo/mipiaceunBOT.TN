"""
Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti.
"""
import logging
import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import GREEN, RED, YELLOW, RESET,CATEGORY_QUESTIONS, user_data, bot, CATEGORY_NAMES, announce_timeout
from modules.user_announcements_interactions.announcement_compiler import send_preview, send_clean_message
from modules.buttons import send_main_menu

# Dizionario per tenere traccia dei messaggi di errore
error_messages = {}

# ------------------------ RACCOLTA DATI UTENTE ------------------------
# --- Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti. ---
@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    user = message.from_user
    user_id = user.id
    
    # Gestisci solo utenti con sessione attiva e categoria impostata
    if user_id not in user_data or not user_data[user_id].get("category"):
        return

    # Se c'è un messaggio di errore precedente per questo utente, eliminalo
    if user_id in error_messages:
        try:
            await client.delete_messages(
                chat_id=message.chat.id,
                message_ids=error_messages[user_id]
            )
            del error_messages[user_id]
        except Exception as e:
            logging.error(f"Errore nell'eliminazione del messaggio di errore: {str(e)}")

    if "user_messages_to_delete" not in user_data[user_id]:
        user_data[user.id]["user_messages_to_delete"] = []
    user_data[user.id]["user_messages_to_delete"].append(message.id)
    try:
        info = user_data[user.id]
        cat = info["category"]
        step = info["step"]

        # Log quando l'utente inizia una nuova pubblicazione (step 0)
        if step == 0:
            category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
            username = user.username if user.username else f"user{user.id}"
            logging.info(f"{GREEN}[NUOVO ANNUNCIO] @{username} ha iniziato la pubblicazione di un {category_name}{RESET}")

        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]
        multi_file = question_data.get("multi_file", False)
        allowed_types = question_data.get("allowed_types", ["text"])

        # --- Inizializzazione files e multi_file_temp_msgs per sicurezza (anche in caso di media group paralleli) ---
        if multi_file:
            if "files" not in info:
                info["files"] = {}
            if label_text not in info["files"]:
                info["files"][label_text] = []
            if "multi_file_temp_msgs" not in info:
                info["multi_file_temp_msgs"] = []

        # --- Gestione domande multi-file ---
        if multi_file:
            # Se arriva /done, termina la raccolta file e passa avanti (accetta sempre /done)
            if message.text and message.text.lower().strip() == "/done":
                # Elimina i messaggi temporanei di conferma file aggiunto
                for mid in info.get("multi_file_temp_msgs", []):
                    try:
                        await client.delete_messages(user.id, mid)
                    except Exception:
                        pass
                info["multi_file_temp_msgs"] = []
                if info["files"][label_text]:
                    info["answers"][label_text] = f"{len(info['files'][label_text])} file allegati."
                else:
                    info["answers"][label_text] = "Nessun file allegato."
                # ...elimina messaggi precedenti e passa avanti...
                if info.get("messages_to_delete"):
                    last_bot_msg = info["messages_to_delete"].pop()
                    try:
                        await client.delete_messages(user.id, last_bot_msg)
                    except Exception:
                        pass
                for mid in user_data[user.id].get("user_messages_to_delete", []):
                    try:
                        await client.delete_messages(user.id, mid)
                    except Exception:
                        pass
                user_data[user.id]["user_messages_to_delete"].clear()
                info["step"] += 1
                if info["step"] < len(CATEGORY_QUESTIONS[cat]):
                    question_data = CATEGORY_QUESTIONS[cat][info["step"]]
                    buttons = [
                        [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
                    ]
                    if question_data.get("skippable"):
                        buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
                    buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
                    sent = await client.send_message(user.id, question_data["question"], reply_markup=InlineKeyboardMarkup(buttons))
                    if "messages_to_delete" not in info:
                        info["messages_to_delete"] = []
                    info["messages_to_delete"].append(sent.id)
                else:
                    preview_id = await send_preview(client, user.id, info)
                    user_data[user.id]["preview_msg_id"] = preview_id
                    confirm_btns = InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user.id}")],
                        [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user.id}")],
                        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                    ])
                    confirm_msg = await client.send_message(user.id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
                    user_data[user.id]["confirm_msg_id"] = confirm_msg.id
                return  # Fine gestione multi-file

            # --- GESTIONE MEDIA GROUP (più foto inviate insieme) ---
            # Se il messaggio fa parte di un media group e contiene foto
            if getattr(message, "media_group_id", None) and message.photo:
                for photo in message.photo if isinstance(message.photo, list) else [message.photo]:
                    await add_file_and_confirm(client, user.id, info, label_text, photo.file_id, "photo")
                return  # Non avanzare step finché non arriva /done

            # Se arriva una foto o documento singolo, aggiungilo alla lista
            if message.photo and not getattr(message, "media_group_id", None):
                await add_file_and_confirm(client, user.id, info, label_text, message.photo.file_id, "photo")
                return
            if message.document:
                await add_file_and_confirm(client, user.id, info, label_text, message.document.file_id, "document")
                return

            # Se arriva testo diverso da /done, ignora o avvisa
            if message.text:
                error_msg = await client.send_message(user.id, "❗ Invia una foto o un documento, oppure premi /done per continuare.")
                error_messages[user_id] = error_msg.id
                return

            # Se arriva altro tipo non gestito (audio, video, ecc.)
            error_msg = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)} oppure /done.")
            error_messages[user_id] = error_msg.id
            return

        # --- Controllo tipo di messaggio per la domanda corrente (SOLO per domande normali) ---
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
        elif not msg_type:  # Se non è stato identificato nessun tipo di messaggio conosciuto
            msg_type = "unknown"
            logging.warning(f"{YELLOW}[ERRORE VALIDAZIONE] @{username} ha inviato un tipo di messaggio non supportato per la domanda '{label_text}'{RESET}")

        if msg_type and msg_type not in allowed_types:
            error_msg = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)}.")
            error_messages[user_id] = error_msg.id
            return

        # --- Gestione domande normali (singolo file o testo) ---
        if message.photo or message.document:
            info["answers"][label_text] = "📎 File allegato."
            info["file"] = message.photo.file_id if message.photo else message.document.file_id
            info["file_type"] = "photo" if message.photo else "document"
        elif message.text:
            if "(opzionale)" in question_text.lower() and message.text.lower().strip() == "/skip":
                info["answers"][label_text] = "Saltato."
            else:
                info["answers"][label_text] = message.text.strip()
        if info.get("messages_to_delete"):
            last_bot_msg = info["messages_to_delete"].pop()
            try:
                await client.delete_messages(user.id, last_bot_msg)
            except Exception:
                pass
        for mid in user_data[user.id].get("user_messages_to_delete", []):
            try:
                await client.delete_messages(user.id, mid)
            except Exception:
                pass
        user_data[user.id]["user_messages_to_delete"].clear()
        info["step"] += 1
        if info["step"] < len(CATEGORY_QUESTIONS[cat]):
            question_data = CATEGORY_QUESTIONS[cat][info["step"]]
            buttons = [
                [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
            ]
            if question_data.get("skippable"):
                buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
            buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
            sent = await client.send_message(user.id, question_data["question"], reply_markup=InlineKeyboardMarkup(buttons))
            if "messages_to_delete" not in info:
                info["messages_to_delete"] = []
            info["messages_to_delete"].append(sent.id)
        else:
            preview_id = await send_preview(client, user.id, info)
            user_data[user.id]["preview_msg_id"] = preview_id
            confirm_btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user.id}")],
                [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user.id}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            confirm_msg = await client.send_message(user.id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
            user_data[user.id]["confirm_msg_id"] = confirm_msg.id
    except Exception as e:
        logging.exception(f"{YELLOW}Errore nella raccolta dei dati durante la compilazione dell'annuncio.{YELLOW}")
        await cleanup_user_data_and_messages(client, user.id, reason="❗ Si è verificato un errore durante la compilazione dell'annuncio.")

async def add_file_and_confirm(client, user_id, info, label_text, file_id, file_type):
    info["files"][label_text].append({"file_id": file_id, "file_type": file_type})
    sent = await client.send_message(
        user_id,
        f"✅ File aggiunto ({len(info['files'][label_text])}). Invia altri file o premi /done per continuare."
    )
    info["multi_file_temp_msgs"].append(sent.id)

# --- Funzione di cleanup dati e messaggi utente ---
async def cleanup_user_data_and_messages(client, user_id, reason="", cleanup_type=""):
    info = user_data.get(user_id)
    if not info:
        return

    # Log dell'interruzione della pubblicazione
    try:
        user = await client.get_users(user_id)
        username = user.username if user.username else f"user{user.id}"
        category = info.get("category")
        if category:
            category_name = {
                "job": "Annuncio di Lavoro",
                "project": "Progetto",
                "event": "Evento",
                "profile": "Profilo"
            }.get(category, category.capitalize() if category else "")
            
            if cleanup_type == "timeout":
                logging.info(f"{YELLOW}[TIMEOUT ANNUNCIO] @{username} non ha completato la pubblicazione di un {category_name} entro il tempo limite{RESET}")
            elif cleanup_type == "cancel":
                logging.info(f"{RED}[ANNUNCIO ANNULLATO] @{username} ha annullato la pubblicazione di un {category_name}{RESET}")
            else:
                logging.info(f"{YELLOW}[PUBBLICAZIONE INTERROTTA] @{username} ha interrotto la pubblicazione di un {category_name}{RESET}")
    except Exception as e:
        logging.error(f"Errore nel logging della cancellazione annuncio: {str(e)}")

    # Cancella messaggi temporanei
    for mid in info.get("messages_to_delete", []):
        try:
            await client.delete_messages(user_id, mid)
        except Exception:
            pass
    for mid in info.get("multi_file_temp_msgs", []):
        try:
            await client.delete_messages(user_id, mid)
        except Exception:
            pass
            
    # Elimina eventuali messaggi di errore
    if user_id in error_messages:
        try:
            # In una chat privata, chat_id e user_id sono la stessa cosa
            await client.delete_messages(
                chat_id=user_id,  # In una chat privata, questo è equivalente a message.chat.id
                message_ids=error_messages[user_id]
            )
            del error_messages[user_id]
        except Exception as e:
            logging.error(f"Errore nell'eliminazione del messaggio di errore durante il cleanup: {str(e)}")
            # Rimuoviamo comunque il riferimento dal dizionario
            del error_messages[user_id]
    for mid in info.get("user_messages_to_delete", []):
        try:
            await client.delete_messages(user_id, mid)
        except Exception:
            pass
    # Rimuovi dati utente
    user_data.pop(user_id, None)
    # Avvisa l'utente e riporta al menu
    msg = "⏱️ Tempo scaduto, i dati inseriti sono stati eliminati. Sei tornato al Menù."
    if reason:
        msg = f"{reason}\n\n{msg}"
    await send_main_menu(client, user_id, msg)

# --- Timeout automatico per la compilazione (3 minuti) ---
async def start_compilation_timeout(client, user_id, announce_timeout):
    await asyncio.sleep(announce_timeout)
    # Cleanup solo se l'utente ha davvero iniziato la compilazione (ha una categoria)
    if user_id in user_data and user_data[user_id].get("category"):
        await cleanup_user_data_and_messages(client, user_id, cleanup_type="timeout")