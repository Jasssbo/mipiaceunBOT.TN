"""
Handler per tutte le interazioni con i bottoni InlineKeyboard.
"""
import logging
import asyncio
import hashlib
import hmac
from typing import List
from pyrogram import filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import (
    CATEGORY_QUESTIONS, CATEGORY_NAMES, bot, BOT_TOKEN, CHAT_ID, YELLOW, GREEN, RED, BLUE, RESET,
    POINTER_MESSAGE_IDS, announce_timeout, report_timeout, MAX_ANNOUNCEMENTS_PER_DAY
)
from modules.user_announcements_interactions.utils.message_utils import send_clean_message, safe_delete
from modules.permissions.user_permissions import is_user_allowed_by_username
from core.session_manager import UserSession, get_announcement_sessions, get_report_sessions
from services.message_service import get_message_service
from core.ui_components import build_main_menu_keyboard, build_back_to_menu_keyboard, build_cancel_report_keyboard

# Get service instances
announcement_sessions = get_announcement_sessions()
report_sessions = get_report_sessions()
msg_service = get_message_service()


def encode_msg_ids(ann_ids: List[int]) -> str:
    """Codifica gli ID dei messaggi in modo compatto (es. '100-105' se contigui) per rispettare il limite di 64 byte."""
    if not ann_ids:
        return ""
    if len(ann_ids) > 2 and ann_ids == list(range(ann_ids[0], ann_ids[-1] + 1)):
        return f"{ann_ids[0]}-{ann_ids[-1]}"
    return ",".join(str(i) for i in ann_ids)


def decode_msg_ids(ids_str: str) -> List[int]:
    """Decodifica la stringa degli ID dei messaggi (supporta sia range 'start-end' che lista separata da virgole)."""
    if not ids_str or ids_str == "None":
        return []
    if "-" in ids_str and "," not in ids_str:
        start_s, end_s = ids_str.split("-", 1)
        start_i, end_i = int(start_s), int(end_s)
        if 0 < end_i - start_i <= 15 and start_i > 0:
            return list(range(start_i, end_i + 1))
        raise ValueError("Intervallo ID non valido")
    result = [int(i) for i in ids_str.split(",") if i and i != "None"]
    if len(result) > 15 or any(i <= 0 for i in result):
        raise ValueError("Lista ID non valida")
    return result


def sign_delete_callback(owner_id: int, ann_ids: List[int]) -> str:
    """
    Genera un callback_data firmato con HMAC-SHA256 (troncato a 10 hex) per prevenire
    la manomissione degli ID dei messaggi da eliminare nel gruppo (OWASP A01/A08)
    e rispettare il limite di 64 byte di Telegram per callback_data.
    Formato: delete_{owner_id}_{ids_encoded}_{sig10}
    """
    ids_encoded = encode_msg_ids(ann_ids)
    payload = f"{owner_id}_{ids_encoded}"
    sig = hmac.new(
        (BOT_TOKEN or "").encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]
    return f"delete_{payload}_{sig}"


def verify_delete_callback(owner_id: int, ids_encoded: str, sig: str) -> bool:
    """Verifica in tempo costante la firma HMAC del bottone di eliminazione annuncio."""
    payload = f"{owner_id}_{ids_encoded}"
    expected = hmac.new(
        (BOT_TOKEN or "").encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]
    return hmac.compare_digest(sig, expected)



# --- Funzione per inviare il menu principale all'utente ---
async def send_main_menu(client, user_id, msg="🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?"):
    keyboard = build_main_menu_keyboard()
    session = await announcement_sessions.get_session(user_id)
    if not session:
        session = UserSession(user_id=user_id, step=0, category=None)
    await send_clean_message(client, user_id, user_id, msg, keyboard, session=session)

# ------------------------ BUTTONS CALLBACK HANDLER ------------------------
# buttons_callback_handler: Gestisce tutte le interazioni con i bottoni InlineKeyboard, 
# come la navigazione tra le domande, la conferma o l'annullamento della pubblicazione,
# e il ritorno al menù principale. 
# Ogni blocco gestisce un tipo di callback specifico.

from middleware.permissions import require_group_member

@bot.on_callback_query()
@require_group_member
async def buttons_callback_handler(client, callback_query: CallbackQuery):
    try:
        await _handle_callback(client, callback_query)
    except FloodWait as e:
        logging.warning(f"[RATE LIMIT] FloodWait per l'utente {callback_query.from_user.id}. Attesa di {e.value} secondi.")
        await asyncio.sleep(e.value)
    except Exception as e:
        logging.exception(f"[BUTTONS] Errore inaspettato in buttons_callback_handler: {e}")
        try:
            await callback_query.answer("❌ Si è verificato un errore inaspettato.", show_alert=True)
        except Exception:
            pass

async def _handle_callback(client, callback_query: CallbackQuery):
    user = callback_query.from_user
    if not user:
        return
    raw_username = user.username if user.username else f"user{user.id}"
    username = "".join(ch if ord(ch) >= 32 and ord(ch) != 127 else " " for ch in raw_username)[:40]
    user_id = user.id
    uid = user_id
    data = getattr(callback_query, 'data', None)
    if data is None:
        await callback_query.answer("❌ Errore interno: dati mancanti.", show_alert=True)
        return

    # --- Gestione accettazione termini ---
    if data == "accept_terms":
        logging.info(f"[TERMS] Utente user_id={user_id} ha accettato i termini")
        await callback_query.answer("Grazie per aver accettato!", show_alert=False)
        await client.delete_messages(user.id, callback_query.message.id)
        # Crea la sessione in memoria e salva su Redis in 1 sola scrittura dentro send_clean_message
        session = UserSession(user_id=user.id, step=0, category=None, allowed=True)
        buttons = build_main_menu_keyboard()
        await send_clean_message(
            client,
            user.id,
            callback_query.message.chat.id,
            "Benvenuto! Cosa vuoi pubblicare all'interno della Community?",
            buttons,
            session=session,
        )
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
        logging.info(f"[BUTTONS] Avvio procedura segnalazione per @{username} (user_id={user_id})")
        await callback_query.answer()
        
        # Imposta lo stato e il TTL in 1 sola scrittura su Redis
        await report_sessions.create_session(
            user_id,
            {"step": "awaiting_username"},
            expire=report_timeout,
        )
        
        # Invia istruzioni all'utente con un bottone per annullare
        buttons = build_cancel_report_keyboard()
        await client.send_message(
            user_id, 
            "🔎 Invia l'@username dell'utente che vuoi segnalare oppure inoltra un suo messaggio.\n"
            "⏱️ Hai 10 minuti per completare la segnalazione.\n"
            "❌ Puoi annullare in qualsiasi momento premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return
        
    # --- Gestione annullamento segnalazione tramite bottone ---
    if data == "cancel_report":
        logging.info(f"[REPORT] Annullamento della segnalazione da parte di user_id={user_id}")
        await callback_query.answer("Segnalazione annullata")
        await report_sessions.delete_session(user_id)
        await send_main_menu(client, user_id, "❌ Segnalazione annullata. Sei tornato al menù principale.")
        return

    # --- Gestione eliminazione annuncio SEMPRE, anche senza sessione ---
    if data and data.startswith("delete_"):
        try:
            # Formato callback firmato: delete_{owner_id}_{ids_encoded}_{sig10}
            parts = data.split("_")
            if len(parts) != 4:
                await callback_query.answer("❌ Dati non validi o bottone obsoleto.", show_alert=True)
                return

            owner_id = int(parts[1])
            ids_encoded = parts[2]
            sig = parts[3]

            # SECURITY (OWASP A01): Verifica che l'utente sia il proprietario dell'annuncio
            if callback_query.from_user.id != owner_id:
                logging.warning(f"[SECURITY] Tentativo di eliminazione non autorizzato: user_id={user_id} ha tentato di eliminare l'annuncio del proprietario {owner_id}")
                await callback_query.answer("❌ Solo l'autore dell'annuncio può eliminarlo.", show_alert=True)
                return

            # SECURITY (OWASP A08): Verifica firma crittografica HMAC per impedire eliminazione arbitraria di messaggi nel gruppo
            if not verify_delete_callback(owner_id, ids_encoded, sig):
                logging.warning(f"[SECURITY] Firma HMAC non valida su callback delete_ da user_id={user_id}: {data}")
                await callback_query.answer("❌ Firma di sicurezza non valida.", show_alert=True)
                return

            ann_ids = decode_msg_ids(ids_encoded)
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
        from modules.user_announcements_interactions.announcement_handler import cancel_compilation_timeout
        cancel_compilation_timeout(user_id)
        session = await announcement_sessions.get_session(user_id)
        if session:
            for mid in session.get("messages_to_delete", []):
                await msg_service.delete_message(client, user_id, mid)
        reset_session = UserSession(user_id=user_id, step=0, category=None)
        await send_clean_message(
            client,
            user_id,
            user_id,
            "🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?",
            build_main_menu_keyboard(),
            session=reset_session,
        )
        return

    # Carica la sessione 1 sola volta per tutte le callback successive
    info = await announcement_sessions.get_session(user_id)
    if not info:
        await callback_query.answer("Sessione scaduta o annuncio già gestito. Riavvia il Bot con /start", show_alert=True)
        return

    try:
        if data is None:
            logging.error(f"{YELLOW}[BUTTONS] Callback senza data ricevuta da utente{username}->{uid}. Callback: {callback_query}{RESET}")
            await callback_query.answer("❌ Errore interno: dati mancanti.", show_alert=True)
            return
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            if cat not in CATEGORY_QUESTIONS:
                await callback_query.answer("❌ Categoria non valida.", show_alert=True)
                return

            # Rate limiting giornaliero annunci
            daily_count = await announcement_sessions.get_daily_count(user_id)
            if daily_count >= MAX_ANNOUNCEMENTS_PER_DAY:
                await callback_query.answer(
                    f"⚠️ Hai raggiunto il limite massimo di {MAX_ANNOUNCEMENTS_PER_DAY} annunci al giorno. Riprova domani!",
                    show_alert=True,
                )
                return

            category_name = CATEGORY_NAMES.get(cat, cat.capitalize())
            logging.info(f"{BLUE}[NUOVO ANNUNCIO] @{username} (user_id={user_id}) ha iniziato la compilazione di: {category_name}{RESET}")

            # Elimina il messaggio del menu principale (se esiste)
            try:
                await client.delete_messages(user_id, callback_query.message.id)
            except Exception:
                pass
            # Inizializza la sessione utente e invia la prima domanda con 1 sola scrittura su Redis
            new_sess = UserSession(user_id=user_id, category=cat, step=0)
            from modules.user_announcements_interactions.announcement_handler import reschedule_compilation_timeout
            await reschedule_compilation_timeout(client, user_id, announce_timeout, sync_redis_ttl=False)
            await send_clean_message(
                client,
                user_id,
                user_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ]),
                session=new_sess,
            )
        # --- Conferma pubblicazione annuncio ---
        elif data.startswith("confirm_"):
            uid = int(data.split("_")[1])
            if callback_query.from_user.id != uid:
                await callback_query.answer("❌ Azione non autorizzata.", show_alert=True)
                return
            user = await client.get_users(uid)
            from modules.user_announcements_interactions.announcement_handler import (
                publish_announcement, cancel_compilation_timeout
            )
            cancel_compilation_timeout(uid)
            # Pubblica l'annuncio nel gruppo e salva tutti gli id dei messaggi pubblicati
            result = await publish_announcement(client, uid, info)
            if not result:
                await callback_query.answer("Errore durante la pubblicazione", show_alert=True)
                return
            
            await announcement_sessions.increment_daily_count(uid)
            msg_id = result['message_id']
            ann_media_ids = result['media_ids']
            cat_name = CATEGORY_NAMES.get(info.get("category"), str(info.get("category")))
            logging.info(f"{GREEN}[ANNUNCIO PUBBLICATO] @{username} (user_id={uid}) ha pubblicato '{cat_name}' nel gruppo (ID: {msg_id}){RESET}")

            # Elimina la vecchia preview senza ID prima di inviare quella nuova con ID
            old_noid_ids = info.get("preview_noid_msg_ids") or []
            old_preview_id = info.get("preview_msg_id")
            ids_to_clean = list(old_noid_ids)
            if isinstance(old_preview_id, list):
                ids_to_clean.extend(old_preview_id)
            elif isinstance(old_preview_id, int):
                ids_to_clean.append(old_preview_id)
            for mid in set(ids_to_clean):
                await msg_service.delete_message(client, uid, mid)
            
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
                if len(multi_file_list) == 1:
                    f = multi_file_list[0]
                    if f["file_type"] == "photo":
                        sent = await client.send_photo(uid, f["file_id"], caption=text[:1024])
                    else:
                        sent = await client.send_document(uid, f["file_id"], caption=text[:1024])
                    preview_with_ids = [sent.id]
                else:
                    from pyrogram.types import InputMediaPhoto, InputMediaDocument
                    media = []
                    for idx, f in enumerate(multi_file_list[:10]):
                        cap = text[:1024] if idx == 0 else None
                        if f["file_type"] == "photo":
                            media.append(InputMediaPhoto(f["file_id"], caption=cap))
                        else:
                            media.append(InputMediaDocument(f["file_id"], caption=cap))
                    sent_msgs = await client.send_media_group(uid, media)
                    preview_with_ids = [m.id for m in sent_msgs]
            else:
                file_id = info.get("file")
                file_type = info.get("file_type")
                if file_id:
                    if file_type == "photo":
                        sent = await client.send_photo(uid, file_id, caption=text[:1024])
                    else:
                        sent = await client.send_document(uid, file_id, caption=text[:1024])
                    preview_with_ids = [sent.id]
                else:
                    sent = await client.send_message(uid, text)
                    preview_with_ids = [sent.id]
            await client.delete_messages(uid, callback_query.message.id)
            conferma = (
                f"✅ Annuncio pubblicato!\n"
                f"ID annuncio: {msg_id}\n"
                f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
            )
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=sign_delete_callback(uid, ann_media_ids))],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await client.send_message(uid, conferma, reply_markup=menu_btn)
            # --- Cleanup dati utente dopo pubblicazione (1 solo DEL, evitando 2 SET inutili prima del DEL) ---
            await announcement_sessions.delete_session(uid)
        # --- Annullamento pubblicazione annuncio ---
        elif data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            if callback_query.from_user.id != uid:
                await callback_query.answer("❌ Azione non autorizzata.", show_alert=True)
                return
            if info:
                preview_id = info.get("preview_msg_id")
                preview_noid_ids = info.get("preview_noid_msg_ids") or []
                confirm_id = info.get("confirm_msg_id")
                ids_to_del = list(preview_noid_ids)
                if isinstance(preview_id, list):
                    ids_to_del.extend(preview_id)
                elif isinstance(preview_id, int):
                    ids_to_del.append(preview_id)
                for mid in set(ids_to_del):
                    await msg_service.delete_message(client, uid, mid)
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
            from modules.user_announcements_interactions.announcement_handler import reschedule_compilation_timeout
            await reschedule_compilation_timeout(client, user_id, announce_timeout, sync_redis_ttl=False)
            if info["step"] > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                cat = info["category"]
                category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
                total_steps = len(CATEGORY_QUESTIONS[cat])
                logging.info(
                    f"{YELLOW}[COMPILAZIONE {category_name}] @{username} è tornato alla domanda precedente "
                    f"(step {info['step'] + 1}/{total_steps}){RESET}"
                )
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
                    InlineKeyboardMarkup(buttons),
                    session=info,
                )
        # --- Salta la domanda corrente ---
        elif data == "skip_question":
            from modules.user_announcements_interactions.announcement_handler import reschedule_compilation_timeout
            await reschedule_compilation_timeout(client, user_id, announce_timeout, sync_redis_ttl=False)
            cat = info["category"]
            step = info["step"]
            total_steps = len(CATEGORY_QUESTIONS[cat])
            category_name = CATEGORY_NAMES.get(cat, cat.capitalize() if cat else "")
            label_text = CATEGORY_QUESTIONS[cat][step]["label"]
            info["answers"][label_text] = "Saltato."
            logging.info(
                f"{YELLOW}[COMPILAZIONE {category_name}] @{username} (step {step + 1}/{total_steps}) "
                f"ha saltato '{label_text}'{RESET}"
            )
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
                await send_clean_message(
                    client,
                    user_id,
                    user_id,
                    next_q,
                    InlineKeyboardMarkup(buttons),
                    session=info,
                )
            else:
                logging.info(f"{BLUE}[ANTEPRIMA {category_name}] @{username} ha completato tutte le domande, invio anteprima di conferma{RESET}")
                from modules.user_announcements_interactions.announcement_handler import send_preview
                preview_id = await send_preview(client, user_id, info)
                info["preview_msg_id"] = preview_id
                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                    [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(user_id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
                if confirm_msg:
                    info["confirm_msg_id"] = confirm_msg.id
                await announcement_sessions.save_session(info, expire=announce_timeout + 30)
        else:
            logging.warning(f"[BUTTONS] Callback non riconosciuta: {data} da utente {user_id}")
            await callback_query.answer("❌ Azione non riconosciuta.", show_alert=True)
    except Exception as e:
        logging.exception(f"Errore nel callback handler. Utente: {uid}, Data: {data}")
        await send_clean_message(client, user_id, user_id, "❌ Si è verificato un errore. Riprova o torna al menù con /start.")
