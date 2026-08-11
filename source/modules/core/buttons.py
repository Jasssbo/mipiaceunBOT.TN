"""
Handler per tutte le interazioni con i bottoni InlineKeyboard.
"""
import logging
import asyncio
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import CATEGORY_QUESTIONS, bot, CHAT_ID, YELLOW, GREEN, RED, BLUE, RESET, POINTER_MESSAGE_IDS, announce_timeout
from modules.user_announcements_interactions.utils.message_utils import send_clean_message, safe_delete
from modules.permissions.topic_permissions import is_user_allowed_by_username
from core.session_manager import get_announcement_sessions, get_report_sessions
from services.message_service import get_message_service
from core.ui_components import build_main_menu_keyboard, build_back_to_menu_keyboard, build_cancel_report_keyboard

# Get service instances
announcement_sessions = get_announcement_sessions()
report_sessions = get_report_sessions()
msg_service = get_message_service()

# Funzione per gestire il timeout della segnalazione
async def async_timeout_report_state(client, user_id, timeout_seconds=300):
    """
    Funzione che gestisce il timeout della segnalazione. 
    Dopo timeout_seconds secondi, se l'utente non ha completato la segnalazione,
    il suo stato viene rimosso.
    """
    try:
        await asyncio.sleep(timeout_seconds)
        
        # Verifica se l'utente è ancora nello stato di segnalazione
        if report_sessions.has_session(user_id):
            # Rimuove lo stato dell'utente
            report_sessions.delete_session(user_id)
            logging.info(f"[TIMEOUT] Stato di segnalazione rimosso per user_id={user_id} dopo {timeout_seconds} secondi")
            
            # Informa l'utente
            try:
                await client.send_message(
                    user_id,
                    "⏱ La procedura di segnalazione è scaduta per inattività.\n"
                    "Per segnalare un utente, premi nuovamente il pulsante 'Segnala utente'."
                )
            except Exception as e:
                logging.error(f"[TIMEOUT] Errore nell'invio del messaggio di timeout: {e}")
    except Exception as e:
        logging.error(f"[TIMEOUT] Errore nel task di timeout: {e}")

# --- Funzione per inviare il menu principale all'utente ---
async def send_main_menu(client, user_id, msg="🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?"):
    keyboard = build_main_menu_keyboard()
    # Ensure a basic session exists for tracking the menu message
    if not announcement_sessions.has_session(user_id):
        announcement_sessions.create_session(user_id, {
            "step": 0,
            "answers": {},
            "messages_to_delete": [],
            "category": None
        })
    await send_clean_message(client, user_id, user_id, msg, keyboard)

# ------------------------ BUTTONS CALLBACK HANDLER ------------------------
# buttons_callback_handler: Gestisce tutte le interazioni con i bottoni InlineKeyboard, 
# come la navigazione tra le domande, la conferma o l'annullamento della pubblicazione,
# e il ritorno al menù principale. 
# Ogni blocco gestisce un tipo di callback specifico.

@bot.on_callback_query()
async def buttons_callback_handler(client, callback_query: CallbackQuery):
    user = callback_query.from_user
    username = user.username if user.username else f"user{user.id}"
    user_id = callback_query.from_user.id
    uid = user_id
    data = getattr(callback_query, 'data', None)
    if data is None:
        await callback_query.answer("❌ Errore interno: dati mancanti.", show_alert=True)
        return

    # --- Gestione segnalazione utente ---
    if data == "accept_terms":
        logging.info(f"[TERMS] Utente user_id={user_id} ha accettato i termini")
        await callback_query.answer("Grazie per aver accettato!", show_alert=False)
        await client.delete_messages(user.id, callback_query.message.id)
        # Initialize session for the user
        announcement_sessions.create_session(user.id, {
            "step": 0,
            "answers": {},
            "messages_to_delete": [],
            "last_bot_message_id": None,
            "file": None,
            "file_type": None,
            "category": None,
            "preview_msg_id": None,
            "confirm_msg_id": None,
            "allowed": True
        })
        buttons = build_main_menu_keyboard()
        await send_clean_message(client, user.id, callback_query.message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)
        return
        
    if data == "read_terms":
        await callback_query.answer()
        # Richiama l'handler di report_user.py che gestisce /terms (tramite testo) o invia direttamente
        text = (
            "📜 **TERMINI DI SERVIZIO** 📜\n\n"
            "mipiaceunBOT è una piattaforma comunitaria per professionisti creativi.\n\n"
            "✅ **Puoi:**\n"
            "• Pubblicare annunci di lavoro, eventi, progetti e profili\n"
            "• Segnalare comportamenti inappropriati\n"
            "• Richiedere la cancellazione dei tuoi dati\n\n"
            "❌ **Non puoi:**\n"
            "• Pubblicare contenuti illegali, molesti o diffamatori\n"
            "• Impersonare altre persone o professionisti\n"
            "• Pubblicare annunci falsi o ingannevoli\n"
            "• Abusare del sistema di segnalazione\n"
            "• Utilizzare il bot per spam o attività fraudolente\n\n"
            "⚠️ **Responsabilità:**\n"
            "• Sei responsabile delle informazioni che pubblichi\n"
            "• Il bot facilita le connessioni ma non è responsabile "
            "degli accordi tra utenti\n"
            "• Le qualifiche professionali dichiarate non sono verificate dalla piattaforma\n\n"
            "📄 Termini completi: https://github.com/Jasssbo/mipiaceunBOT.TN/blob/main/TERMS_OF_SERVICE.md"
        )
        await client.send_message(user_id, text)
        return
        
    if data == "read_privacy":
        await callback_query.answer()
        text = (
            "🔒 **INFORMATIVA SULLA PRIVACY** 🔒\n\n"
            "mipiaceunBOT è uno strumento della community per aiutare professionisti "
            "creativi a condividere il proprio lavoro e trovare opportunità.\n\n"
            "📋 **Dati che conserviamo:**\n"
            "• Segnalazioni: ID utente segnalato, ID segnalatore, motivazione e data\n"
            "• Gli annunci pubblicati sono visibili nel gruppo Telegram pubblico\n\n"
            "📋 **Dati che NON conserviamo:**\n"
            "• Non salviamo i tuoi messaggi privati con il bot\n"
            "• Non salviamo dati personali al di fuori delle segnalazioni\n"
            "• Le sessioni di compilazione sono temporanee e vengono eliminate\n\n"
            "🔑 **I tuoi diritti:**\n"
            "• /my_data — Vedi tutti i dati che abbiamo su di te\n"
            "• /erase_my_data — Cancella tutti i tuoi dati\n"
            "• /terms — Leggi i termini di servizio\n\n"
            "📧 **Contatti:**\n"
            "Per domande sulla privacy, contatta l'amministratore del gruppo "
            "o apri un issue su GitHub.\n\n"
            "⚖️ Questo servizio opera nel rispetto del GDPR (Regolamento UE 2016/679). "
            "I dati sono trattati esclusivamente per finalità di moderazione della community."
        )
        await client.send_message(user_id, text)
        return

    # --- Gestione segnalazione utente ---
    if data == "report_user":
        logging.info(f"[BUTTONS] Avvio procedura segnalazione per user_id={user_id}")
        await callback_query.answer()
        
        # Crea un nuovo task per il timeout
        timeout_task = client.loop.create_task(async_timeout_report_state(client, user_id, 300))
        
        # Imposta lo stato e salva il task di timeout
        report_sessions.create_session(user_id, {
            "step": "awaiting_username", 
            "timeout_task": timeout_task
        })
        
        # Invia istruzioni all'utente con un bottone per annullare
        buttons = build_cancel_report_keyboard()
        await client.send_message(
            user_id, 
            "🔎 Invia l'@username dell'utente che vuoi segnalare oppure inoltra un suo messaggio.\n"
            "⏱️ Hai 5 minuti per completare la segnalazione.\n"
            "❌ Puoi annullare in qualsiasi momento premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return
        
    # --- Gestione annullamento segnalazione tramite bottone ---
    if data == "cancel_report":
        logging.info(f"[REPORT] Annullamento della segnalazione da parte di user_id={user_id}")
        await callback_query.answer("Segnalazione annullata")
        
        # Verifica se l'utente è in stato di segnalazione
        if report_sessions.has_session(user_id):
            session = report_sessions.get_session(user_id)
            # Cancella il task di timeout se esiste
            if session and "timeout_task" in session:
                try:
                    session["timeout_task"].cancel()
                    logging.info(f"[REPORT] Task timeout cancellato per user_id={user_id}")
                except Exception as e:
                    logging.error(f"[REPORT] Errore nella cancellazione del timeout task: {str(e)} per user_id={user_id}")
            
            # Rimuovi lo stato
            report_sessions.delete_session(user_id)
            
            # Torna al menu principale
            await send_main_menu(client, user_id, "❌ Segnalazione annullata. Sei tornato al menù principale.")
        return

    # --- Gestione eliminazione annuncio SEMPRE, anche senza sessione ---
    if data and data.startswith("delete_"):
        try:
            # Formato callback: delete_{owner_id}_{ann_ids}_{preview_ids}
            parts = data.split("_")
            if len(parts) < 3:
                await callback_query.answer("❌ Dati non validi.", show_alert=True)
                return
            
            owner_id = int(parts[1])
            ann_ids = [int(i) for i in parts[2].split(",") if i and i != 'None']
            
            # SECURITY: Verifica che l'utente sia il proprietario dell'annuncio
            if callback_query.from_user.id != owner_id:
                logging.warning(f"[SECURITY] Tentativo di eliminazione non autorizzato: user_id={user_id} ha tentato di eliminare l'annuncio del proprietario {owner_id}")
                await callback_query.answer("❌ Solo l'autore dell'annuncio può eliminarlo.", show_alert=True)
                return
            
            user = callback_query.from_user

            if ann_ids:
                first_ann_id = ann_ids[0] if ann_ids else '-'
                logging.info(f"[ELIMINAZIONE ANNUNCIO] user_id={user_id} ha eliminato il proprio annuncio (ID: {first_ann_id})")
                await client.delete_messages(CHAT_ID, ann_ids)

            await client.delete_messages(user.id, callback_query.message.id)
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await client.send_message(
                user.id,
                f"✅ Annuncio eliminato con successo.\nID annuncio: {first_ann_id if ann_ids else '-'}",
                reply_markup=menu_btn
            )
            await callback_query.answer("Hai cancellato il tuo annuncio.", show_alert=False)
        except Exception as e:
            logging.exception(f"Errore imprevisto in fase di eliminazione dell'annuncio tramite bottone.")
            await callback_query.answer("❌ Errore durante l'eliminazione.", show_alert=True)
        return

    # --- Ritorno al menù principale SEMPRE consentito ---
    if data == "back_to_menu":
        user = await client.get_users(user_id)
        if not await is_user_allowed_by_username(client, user):
            await client.send_message(user_id, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
            return
        # Prova a eliminare eventuali messaggi da eliminare, se esistono
        if announcement_sessions.has_session(user_id):
            session = announcement_sessions.get_session(user_id)
            if session:
                for mid in session.get("messages_to_delete", []):
                    await msg_service.delete_message(client, user_id, mid)
            announcement_sessions.delete_session(user_id)
        await send_main_menu(client, user_id)
        return

    # Se la sessione non esiste, gestisci solo le altre callback (ma NON il menu)
    if not announcement_sessions.has_session(user_id):
        await callback_query.answer("Sessione scaduta o annuncio già gestito. Riavvia il Bot con /start", show_alert=True)
        return

    try:
        if data is None:
            logging.error(f"{YELLOW}[BUTTONS] Callback senza data ricevuta da utente{username}->{uid}. Callback: {callback_query}{RESET}")
            await callback_query.answer("❌ Errore interno: dati mancanti.", show_alert=True)
            return
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            # Elimina il messaggio del menu principale (se esiste)
            try:
                await client.delete_messages(user_id, callback_query.message.id)
            except Exception:
                pass
            # Inizializza la sessione utente SOLO ora
            announcement_sessions.create_session(user_id, {
                "category": cat,
                "step": 0,
                "answers": {},
                "file": None,
                "file_type": None,
                "messages_to_delete": [],
                "user_messages_to_delete": [],
                "timeout_task": None
            })
            # Avvia il timeout solo ora
            from modules.user_announcements_interactions.announcement_handler import start_compilation_timeout
            session = announcement_sessions.get_session(user_id)
            if session and session.get("timeout_task") is None:
                session["timeout_task"] = asyncio.create_task(
                    start_compilation_timeout(client, user_id, announce_timeout)
                )
            # Invia la prima domanda e salva l'ID per poterla eliminare dopo
            first_question_id = await send_clean_message(
                client,
                user_id,
                user_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
            )
            # `send_clean_message` aggiorna già session['messages_to_delete']
        # --- Conferma pubblicazione annuncio ---
        elif data.startswith("confirm_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            info = announcement_sessions.get_session(uid)
            if not info:
                await callback_query.answer("Sessione scaduta", show_alert=True)
                return
            # Pubblica l'annuncio nel gruppo e salva tutti gli id dei messaggi pubblicati
            from modules.user_announcements_interactions.announcement_handler import publish_announcement
            result = await publish_announcement(client, uid, info)
            if not result:
                await callback_query.answer("Errore durante la pubblicazione", show_alert=True)
                return
            
            msg_id = result['message_id']
            ann_media_ids = result['media_ids']
            
            # Invia una nuova preview privata con ID e bottoni, salva tutti gli id
            from modules.user_announcements_interactions.announcement_handler import build_announcement_text
            text = build_announcement_text(info, user, show_id=msg_id)
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
                sent_msgs = await client.send_media_group(uid, media)
                preview_with_ids = [m.id for m in sent_msgs]
            else:
                file_id = info.get("file")
                file_type = info.get("file_type")
                if file_id:
                    if file_type == "photo":
                        sent = await client.send_photo(uid, file_id, caption=text)
                    else:
                        sent = await client.send_document(uid, file_id, caption=text)
                    preview_with_ids = [sent.id]
                else:
                    sent = await client.send_message(uid, text)
                    preview_with_ids = [sent.id]
            info["preview_msg_id"] = preview_with_ids
            await client.delete_messages(uid, callback_query.message.id)
            conferma = (
                f"✅ Annuncio pubblicato!\n"
                f"ID annuncio: {msg_id}\n"
                f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
            )
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=f"delete_{uid}_{','.join(str(i) for i in ann_media_ids)}_{','.join(str(i) for i in preview_with_ids)}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            confirm_msg = await client.send_message(uid, conferma, reply_markup=menu_btn)
            if confirm_msg:
                info["confirm_msg_id"] = confirm_msg.id
            # --- Cleanup dati utente dopo pubblicazione e preview con ID ---
            announcement_sessions.delete_session(uid)
        # --- Annullamento pubblicazione annuncio ---
        elif data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            info = announcement_sessions.get_session(uid)
            if info:
                preview_id = info.get("preview_msg_id")
                confirm_id = info.get("confirm_msg_id")
                if preview_id:
                    await msg_service.delete_message(client, uid, preview_id)
                if confirm_id:
                    await msg_service.delete_message(client, uid, confirm_id)
            
            # Cleanup con tipo specifico per il log
            from modules.user_announcements_interactions.announcement_handler import cleanup_user_data_and_messages
            await cleanup_user_data_and_messages(client, uid, cleanup_type="cancel")
            await send_main_menu(client, uid, "❌ Annuncio annullato. Sei tornato al menù principale.")
        # NB: delete_ è già gestito prima del controllo sessione (linee sopra)
        # Questo ramo non dovrebbe mai essere raggiunto
        elif data.startswith("delete_"):
            pass
        # --- Torna alla domanda precedente ---
        elif data == "back_to_question":
            info = announcement_sessions.get_session(user_id)
            if not info:
                await callback_query.answer("Sessione scaduta", show_alert=True)
                return
            if info["step"] > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                for mid in info["messages_to_delete"]:
                    await msg_service.delete_message(client, user_id, mid)
                info["messages_to_delete"].clear()
                q = CATEGORY_QUESTIONS[info["category"]][info["step"]]["question"]
                question_data = CATEGORY_QUESTIONS[info["category"]][info["step"]]
                buttons = [
                    [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
                ]
                if question_data.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
                await send_clean_message(
                    client,
                    user_id,
                    user_id,
                    q,
                    InlineKeyboardMarkup(buttons)
                )
        # --- Salta la domanda corrente ---
        elif data == "skip_question":
            info = announcement_sessions.get_session(user_id)
            if not info:
                await callback_query.answer("Sessione scaduta", show_alert=True)
                return
            cat = info["category"]
            step = info["step"]
            label_text = CATEGORY_QUESTIONS[cat][step]["label"]
            info["answers"][label_text] = "Saltato."
            info["step"] += 1
            if info["step"] < len(CATEGORY_QUESTIONS[cat]):
                next_question_data = CATEGORY_QUESTIONS[cat][info["step"]]
                next_q = next_question_data["question"]
                buttons = [
                    [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
                ]
                if next_question_data.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
                await send_clean_message(client, user_id, user_id, next_q, InlineKeyboardMarkup(buttons))
            else:
                from modules.user_announcements_interactions.announcement_handler import send_preview
                preview_id = await send_preview(client, user_id, info)
                session = announcement_sessions.get_session(user_id)
                if session:
                    session["preview_msg_id"] = preview_id
                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                    [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(user_id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
                if session:
                    session["confirm_msg_id"] = confirm_msg.id
        else:
            logging.warning(f"[BUTTONS] Callback non riconosciuta: {data} da utente {user_id}")
            await callback_query.answer("❌ Azione non riconosciuta.", show_alert=True)
    except Exception as e:
        logging.exception(f"Errore nel callback handler. Utente: {uid}, Data: {data}")
        await send_clean_message(client, user_id, user_id, "❌ Si è verificato un errore. Riprova o torna al menù con /start.")
