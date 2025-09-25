"""
Handler per la raccolta dati utente (versione webhook).
Gestisce domande, risposte e preview utilizzando Redis per lo stato.
"""
import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import (GREEN, RED, YELLOW, RESET, CATEGORY_QUESTIONS, bot, announce_timeout,
                   get_user_data, set_user_data, delete_user_data)
from modules.user_announcements_interactions.announcement_compiler import send_preview, send_clean_message
from modules.buttons import send_main_menu

# Helper function per aggiungere file in multi-file questions
async def add_file_and_confirm(client, user_id, info, label_text, file_id, file_type):
    """
    Aggiunge un file alla lista per domande multi-file e invia conferma.
    In versione webhook: stesso comportamento ma aggiorna Redis.
    """
    file_entry = {"file_id": file_id, "file_type": file_type}
    info["files"][label_text].append(file_entry)
    
    # Invia messaggio di conferma
    count = len(info["files"][label_text])
    sent = await client.send_message(
        user_id, 
        f"✅ File {count} aggiunto! Invia altri file o scrivi /done per continuare."
    )
    info["multi_file_temp_msgs"].append(sent.id)
    
    # Salva stato aggiornato in Redis
    set_user_data(user_id, info)

async def ask_next_question(client, user_id, info):
    """
    Invia la prossima domanda o la preview finale.
    In versione webhook: carica/salva da Redis.
    """
    cat = info["category"]
    step = info["step"]
    
    if step < len(CATEGORY_QUESTIONS[cat]):
        question_data = CATEGORY_QUESTIONS[cat][step]
        
        # Prepara bottoni
        buttons = [
            [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
        ]
        if question_data.get("skippable"):
            buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
        buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
        
        # Invia domanda
        sent = await client.send_message(
            user_id, 
            question_data["question"], 
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        # Salva ID messaggio da eliminare
        if "messages_to_delete" not in info:
            info["messages_to_delete"] = []
        info["messages_to_delete"].append(sent.id)
        
        # Aggiorna Redis
        set_user_data(user_id, info)
    else:
        # Tutte le domande completate: mostra preview
        preview_id = await send_preview(client, user_id, info)
        info["preview_msg_id"] = preview_id
        
        confirm_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
            [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
            [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
        ])
        confirm_msg = await client.send_message(
            user_id, 
            "✅ Confermi di voler pubblicare questo annuncio?", 
            reply_markup=confirm_btns
        )
        info["confirm_msg_id"] = confirm_msg.id
        
        # Salva stato finale in Redis
        set_user_data(user_id, info)

# ------------------------ RACCOLTA DATI UTENTE ------------------------

@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    """
    Handler per raccolta dati utente.
    In versione webhook: carica sessione da Redis, processa, salva stato aggiornato.
    """
    user = message.from_user
    
    # Carica sessione da Redis invece della memoria
    user_session = get_user_data(user.id)
    if not user_session or not user_session.get("category"):
        return  # Nessuna sessione attiva
    
    # Prepara lista messaggi utente da eliminare
    if "user_messages_to_delete" not in user_session:
        user_session["user_messages_to_delete"] = []
    user_session["user_messages_to_delete"].append(message.id)
    
    try:
        info = user_session
        cat = info["category"]
        step = info["step"]
        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]
        multi_file = question_data.get("multi_file", False)
        allowed_types = question_data.get("allowed_types", ["text"])

        # --- Inizializzazione files e multi_file_temp_msgs per sicurezza ---
        if multi_file:
            if "files" not in info:
                info["files"] = {}
            if label_text not in info["files"]:
                info["files"][label_text] = []
            if "multi_file_temp_msgs" not in info:
                info["multi_file_temp_msgs"] = []

        # --- Gestione domande multi-file ---
        if multi_file:
            # Se arriva /done, termina la raccolta file e passa avanti
            if message.text and message.text.lower().strip() == "/done":
                # Elimina i messaggi temporanei di conferma file aggiunto
                for mid in info.get("multi_file_temp_msgs", []):
                    try:
                        await client.delete_messages(user.id, mid)
                    except Exception:
                        pass
                info["multi_file_temp_msgs"] = []
                
                # Salva risposta
                if info["files"][label_text]:
                    info["answers"][label_text] = f"{len(info['files'][label_text])} file allegati."
                else:
                    info["answers"][label_text] = "Nessun file allegato."
                
                # Elimina messaggi precedenti
                if info.get("messages_to_delete"):
                    last_bot_msg = info["messages_to_delete"].pop()
                    try:
                        await client.delete_messages(user.id, last_bot_msg)
                    except Exception:
                        pass
                
                for mid in info.get("user_messages_to_delete", []):
                    try:
                        await client.delete_messages(user.id, mid)
                    except Exception:
                        pass
                info["user_messages_to_delete"].clear()
                
                # Avanza step
                info["step"] += 1
                
                # Salva stato e continua
                set_user_data(user.id, info)
                await ask_next_question(client, user.id, info)
                return

            # --- GESTIONE MEDIA GROUP (più foto inviate insieme) ---
            if getattr(message, "media_group_id", None) and message.photo:
                for photo in message.photo if isinstance(message.photo, list) else [message.photo]:
                    await add_file_and_confirm(client, user.id, info, label_text, photo.file_id, "photo")
                return

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
                # Salva stato aggiornato
                set_user_data(user.id, info)
                return

            # Se arriva altro tipo non gestito
            sent = await client.send_message(user.id, f"❗ Risposta non valida per questa domanda. Sono ammessi solo: {', '.join(allowed_types)} oppure /done.")
            info["multi_file_temp_msgs"].append(sent.id)
            set_user_data(user.id, info)
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

        # Elimina messaggi precedenti
        if info.get("messages_to_delete"):
            last_bot_msg = info["messages_to_delete"].pop()
            try:
                await client.delete_messages(user.id, last_bot_msg)
            except Exception:
                pass

        for mid in info.get("user_messages_to_delete", []):
            try:
                await client.delete_messages(user.id, mid)
            except Exception:
                pass
        info["user_messages_to_delete"].clear()

        # Avanza step
        info["step"] += 1
        
        # Salva stato aggiornato in Redis
        set_user_data(user.id, info)
        
        # Continua con prossima domanda o preview
        await ask_next_question(client, user.id, info)

    except Exception as e:
        logging.exception(f"[COLLECT_DATA] Errore nel handler per user {user.id}: {e}")
        # In caso di errore, prova a salvare lo stato attuale
        try:
            set_user_data(user.id, user_session)
        except:
            pass


# ------------------------ TIMEOUT MANAGEMENT ------------------------
# NOTA: In versione webhook, start_compilation_timeout NON è più necessario
# Redis TTL gestisce automaticamente la scadenza delle sessioni

async def start_compilation_timeout(client, user_id, timeout_seconds):
    """
    Funzione legacy mantenuta per compatibilità.
    In versione webhook: Redis TTL gestisce automaticamente i timeout.
    Questa funzione non viene più chiamata.
    """
    logging.warning(f"[COLLECT_DATA] start_compilation_timeout chiamata per user {user_id} ma ignorata (versione webhook usa Redis TTL)")
    pass