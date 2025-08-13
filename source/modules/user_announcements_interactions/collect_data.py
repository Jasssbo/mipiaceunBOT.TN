"""
Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti.
"""
import logging
import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import GREEN, RED, YELLOW, RESET,CATEGORY_QUESTIONS, user_data, bot, announce_timeout
from modules.user_announcements_interactions.announcement_compiler import send_preview, send_clean_message
from modules.buttons import send_main_menu

# ------------------------ RACCOLTA DATI UTENTE ------------------------
# --- Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti. ---
@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    user = message.from_user
    # Gestisci solo utenti con sessione attiva e categoria impostata
    if user.id not in user_data or not user_data[user.id].get("category"):
        return
    if "user_messages_to_delete" not in user_data[user.id]:
        user_data[user.id]["user_messages_to_delete"] = []
    user_data[user.id]["user_messages_to_delete"].append(message.id)
    try:
        info = user_data[user.id]
        cat = info["category"]
        step = info["step"]
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
                sent = await client.send_message(user.id, "❗ Invia una foto o un documento, oppure premi /done per continuare.")
                info["multi_file_temp_msgs"].append(sent.id)
                return

            # Se arriva altro tipo non gestito (audio, video, ecc.)
            sent = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)} oppure /done.")
            info["multi_file_temp_msgs"].append(sent.id)
            return

        # --- Controllo tipo di messaggio per la domanda corrente (SOLO per domande normali) ---
        msg_type = None
        if message.text and not message.photo and not message.document:
            msg_type = "text"
        elif message.photo:
            msg_type = "photo"
        elif message.document:
            msg_type = "document"
        elif message.audio:
            msg_type = "audio"
        elif message.voice:
            msg_type = "voice"
        elif message.video:
            msg_type = "video"

        if msg_type and msg_type not in allowed_types:
            await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)}.")
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
async def cleanup_user_data_and_messages(client, user_id, reason=""):
    info = user_data.get(user_id)
    if not info:
        return
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
        await cleanup_user_data_and_messages(client, user_id)