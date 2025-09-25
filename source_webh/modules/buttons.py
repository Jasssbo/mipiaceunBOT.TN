"""
Handler per tutte le interazioni con i bottoni InlineKeyboard (versione webhook).
Sostituisce timeout tasks con TTL Redis e user_data con storage layer.
"""
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import (CATEGORY_QUESTIONS, bot, CHAT_ID, YELLOW, GREEN, RED, RESET, 
                   POINTER_MESSAGE_IDS, announce_timeout, get_user_data, set_user_data, 
                   delete_user_data, get_report_state, set_report_state, delete_report_state)
from modules.user_announcements_interactions.announcement_compiler import (
    send_clean_message, send_preview, update_preview_with_id, publish_announcement, 
    safe_delete, build_announcement_text
)
from modules.topic_guardian import is_user_allowed_by_username

# NOTA: In versione webhook, i timeout asyncio.create_task NON funzionano
# Usiamo Redis TTL invece: set_report_state(user_id, data, ttl=300)

# --- Funzione per inviare il menu principale all'utente ---
async def send_main_menu(client, user_id, msg="🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?"):
    """
    Invia il menu principale. In versione webhook: stessa logica.
    """
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")],
        [InlineKeyboardButton("🚨 Segnala utente", callback_data="report_user")]
    ])
    await send_clean_message(client, user_id, user_id, msg, buttons)

# ------------------------ BUTTONS CALLBACK HANDLER ------------------------

@bot.on_callback_query()
async def buttons_callback_handler(client, callback_query: CallbackQuery):
    """
    Handler per callback queries. 
    In versione webhook: carica/salva stato da Redis invece della memoria.
    """
    user_id = callback_query.from_user.id
    uid = user_id
    data = getattr(callback_query, 'data', None)
    
    if data is None:
        await callback_query.answer("❌ Errore interno: dati mancanti.", show_alert=True)
        return

    # --- Gestione segnalazione utente ---
    if data == "report_user":
        logging.info(f"[BUTTONS] Avvio procedura segnalazione per user_id={user_id}")
        await callback_query.answer()
        
        # In versione webhook: NO asyncio.create_task, usiamo Redis TTL
        # Redis si occupa automaticamente del timeout dopo 300 secondi
        report_data = {
            "step": "awaiting_username",
            "started_at": None  # Potremmo aggiungere timestamp se serve
        }
        
        # Salva con TTL di 5 minuti (300 secondi) - timeout automatico
        if not set_report_state(user_id, report_data, ttl=300):
            await callback_query.answer("❌ Errore interno. Riprova.", show_alert=True)
            return
        
        # Invia istruzioni all'utente con un bottone per annullare
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Annulla segnalazione", callback_data="cancel_report")]
        ])
        await client.send_message(
            user_id, 
            "🔎 Invia l'@username dell'utente che vuoi segnalare oppure inoltra un suo messaggio.\n"
            "⏱️ Hai 5 minuti per completare la segnalazione.\n"
            "❌ Puoi annullare in qualsiasi momento con /annulla o premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return
        
    # --- Gestione annullamento segnalazione tramite bottone ---
    if data == "cancel_report":
        logging.info(f"[BUTTONS] Annullamento segnalazione tramite bottone per user_id={user_id}")
        await callback_query.answer("Segnalazione annullata")
        
        # Rimuovi stato segnalazione da Redis
        delete_report_state(user_id)
        
        # Torna al menu principale
        await send_main_menu(client, user_id, "❌ Segnalazione annullata. Sei tornato al menù principale.")
        return

    # --- Gestione eliminazione annuncio SEMPRE, anche senza sessione ---
    if data and data.startswith("delete_"):
        try:
            parts = data.split("_")
            ann_ids = [int(i) for i in parts[1].split(",") if i and i != 'None']
            user = callback_query.from_user
            if ann_ids:
                await client.delete_messages(CHAT_ID, ann_ids)
            await client.delete_messages(user.id, callback_query.message.id)
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await client.send_message(
                user.id,
                f"✅ Annuncio eliminato con successo.\nID annuncio: {ann_ids[0] if ann_ids else '-'}",
                reply_markup=menu_btn
            )
            await callback_query.answer("Hai cancellato il tuo annuncio.", show_alert=False)
        except Exception as e:
            logging.exception(f"{YELLOW}Errore imprevisto in fase di eliminazione dell'annuncio tramite bottone.{RESET}")
            await callback_query.answer("❌ Errore durante l'eliminazione.", show_alert=True)
        return

    # --- Ritorno al menù principale SEMPRE consentito ---
    if data == "back_to_menu":
        user = await client.get_users(user_id)
        if not await is_user_allowed_by_username(client, user):
            await client.send_message(user_id, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
            return
        
        # Carica user_data da Redis invece della memoria
        user_session = get_user_data(user_id)
        if user_session:
            # Elimina messaggi da pulire
            for mid in user_session.get("messages_to_delete", []):
                await safe_delete(client, user_id, mid)
            # Rimuovi sessione da Redis
            delete_user_data(user_id)
        
        await send_main_menu(client, user_id)
        return

    # --- CONTROLLO SESSIONE per operazioni che richiedono sessione attiva ---
    # Carica sessione da Redis invece della memoria
    user_session = get_user_data(uid)
    if not user_session:
        await callback_query.answer("Sessione scaduta o annuncio già gestito. Riavvia il Bot con /start", show_alert=True)
        return

    try:
        # --- Gestione nuova categoria annuncio ---
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            # Elimina il messaggio del menu principale (se esiste)
            try:
                await client.delete_messages(user_id, callback_query.message.id)
            except Exception:
                pass
            
            # Inizializza la sessione utente in Redis
            user_session = {
                "category": cat,
                "step": 0,
                "answers": {},
                "file": None,
                "file_type": None,
                "messages_to_delete": [],
                "user_messages_to_delete": [],
                # NOTA: In webhook, non abbiamo timeout_task - Redis TTL gestisce scadenza
            }
            
            # Salva sessione con TTL (timeout automatico dopo announce_timeout secondi)
            if not set_user_data(user_id, user_session):
                await callback_query.answer("❌ Errore interno. Riprova.", show_alert=True)
                return
            
            # Invia prima domanda
            await send_clean_message(
                client,
                user_id,
                user_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
            )
        
        # --- Conferma pubblicazione annuncio ---
        elif data.startswith("confirm_"):
            target_uid = int(data.split("_")[1])
            user = await client.get_users(target_uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(target_uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            
            # Ricarica sessione aggiornata da Redis
            info = get_user_data(target_uid)
            if not info:
                await callback_query.answer("Sessione scaduta.", show_alert=True)
                return
            
            # Pubblica l'annuncio nel gruppo e salva tutti gli id dei messaggi pubblicati
            msg = await publish_announcement(client, target_uid, info, POINTER_MESSAGE_IDS)
            ann_media_ids = []
            if "last_ann_media_ids" in info:
                ann_media_ids = info["last_ann_media_ids"]
            else:
                ann_media_ids = [msg.id] if msg else []
            
            # Invia una nuova preview privata con ID e bottoni
            text = build_announcement_text(info, user, show_id=msg.id)
            files = info.get("files", {})
            multi_file_label = None
            multi_file_list = []
            for label, filelist in files.items():
                if filelist:
                    multi_file_label = label
                    multi_file_list = filelist
                    break
            
            preview_with_ids = []
            if multi_file_list:
                from pyrogram.types import InputMediaPhoto, InputMediaDocument
                media = []
                for idx, f in enumerate(multi_file_list):
                    if f["file_type"] == "photo":
                        media.append(InputMediaPhoto(f["file_id"], caption=text if idx == 0 else None))
                    else:
                        media.append(InputMediaDocument(f["file_id"], caption=text if idx == 0 else None))
                sent_msgs = await client.send_media_group(target_uid, media)
                preview_with_ids = [m.id for m in sent_msgs]
            else:
                file_id = info.get("file")
                file_type = info.get("file_type")
                if file_id:
                    if file_type == "photo":
                        sent = await client.send_photo(target_uid, file_id, caption=text)
                    else:
                        sent = await client.send_document(target_uid, file_id, caption=text)
                    preview_with_ids = [sent.id]
                else:
                    sent = await client.send_message(target_uid, text)
                    preview_with_ids = [sent.id]
            
            # Bottoni per gestire l'annuncio pubblicato
            ann_ids_str = ",".join(map(str, ann_media_ids))
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Elimina Annuncio", callback_data=f"delete_{ann_ids_str}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            
            await client.send_message(
                target_uid,
                "✅ Il tuo annuncio è stato pubblicato con successo!",
                reply_markup=buttons
            )
            
            # Rimuovi sessione utente da Redis
            delete_user_data(target_uid)
            
        # --- Altri tipi di callback (skip, next, etc) ---
        elif data == "skip":
            # Ricarica sessione da Redis
            user_session = get_user_data(uid)
            if not user_session:
                await callback_query.answer("Sessione scaduta.", show_alert=True)
                return
            
            current_step = user_session["step"]
            category = user_session["category"]
            questions = CATEGORY_QUESTIONS[category]
            
            if current_step < len(questions):
                # Salta la domanda corrente
                user_session["answers"][str(current_step)] = "⏭️ Saltata"
                user_session["step"] += 1
                
                # Salva stato aggiornato in Redis
                set_user_data(uid, user_session)
                
                # Continua con la prossima domanda
                from modules.user_announcements_interactions.collect_data import ask_next_question
                await ask_next_question(client, uid, user_session)
        
        elif data == "next":
            # Logica simile per "next" - caricare da Redis, aggiornare, salvare
            pass
            
        # Altri handler...
        
        await callback_query.answer()
        
    except Exception as e:
        logging.exception(f"[BUTTONS] Errore nel callback handler: {e}")
        await callback_query.answer("❌ Errore interno.", show_alert=True)