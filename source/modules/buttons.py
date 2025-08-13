"""
Handler per tutte le interazioni con i bottoni InlineKeyboard.
"""
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import CATEGORY_QUESTIONS, user_data, bot, CHAT_ID, YELLOW, GREEN, RED, RESET, POINTER_MESSAGE_IDS, announce_timeout
from modules.user_announcements_interactions.announcement_compiler import send_clean_message, send_preview, update_preview_with_id, publish_announcement, is_user_allowed_by_username, safe_delete
from modules.topic_guardian import is_user_allowed_by_username

# --- Funzione per inviare il menu principale all'utente ---
async def send_main_menu(client, user_id, msg="🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?"):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
    ])
    await send_clean_message(client, user_id, user_id, msg, buttons)

# ------------------------ BUTTONS CALLBACK HANDLER ------------------------
# buttons_callback_handler: Gestisce tutte le interazioni con i bottoni InlineKeyboard, 
# come la navigazione tra le domande, la conferma o l'annullamento della pubblicazione,
# e il ritorno al menù principale. Ogni blocco gestisce un tipo di callback specifico.
@bot.on_callback_query()
async def buttons_callback_handler(client, callback_query: CallbackQuery):
    uid = callback_query.from_user.id
    # --- Controllo esistenza dati utente ---
    data = callback_query.data
    user_id = callback_query.from_user.id
    # Gestione eliminazione annuncio SEMPRE, anche senza sessione
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
        # Prova a eliminare eventuali messaggi da eliminare, se esistono
        if user_id in user_data:
            for mid in user_data[user_id].get("messages_to_delete", []):
                await safe_delete(client, user_id, mid)
            user_data.pop(user_id, None)
        await send_main_menu(client, user_id)
        return
    # Se la sessione non esiste, gestisci solo le altre callback (ma NON il menu)
    if uid not in user_data:
        await callback_query.answer("Sessione scaduta o annuncio già gestito. Riavvia il Bot con /start", show_alert=True)
        return
    try:
        if data is None:
            logging.error(f"[BUTTONS] Callback senza data ricevuta da utente {uid}. Callback: {callback_query}")
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
            user_data[user_id] = {
                "category": cat,
                "step": 0,
                "answers": {},
                "file": None,
                "file_type": None,
                "messages_to_delete": [],
                "user_messages_to_delete": [],
                "timeout_task": None
            }
            # Avvia il timeout solo ora
            import asyncio
            if user_data[user_id]["timeout_task"] is None:
                user_data[user_id]["timeout_task"] = asyncio.create_task(
                    __import__('modules.user_announcements_interactions.collect_data').user_announcements_interactions.collect_data.start_compilation_timeout(client, user_id, announce_timeout)
                )
            await send_clean_message(
                client,
                user_id,
                user_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
            )
        # --- Ritorno al menù principale ---
        elif data == "back_to_menu":
            user = await client.get_users(user_id)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(user_id, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            if user_id in user_data:
                for mid in user_data[user_id].get("messages_to_delete", []):
                    await safe_delete(client, user_id, mid)
                user_data.pop(user_id, None)
            await send_main_menu(client, user_id)
        # --- Conferma pubblicazione annuncio ---
        elif data.startswith("confirm_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            info = user_data[uid]
            # Pubblica l'annuncio nel gruppo e salva tutti gli id dei messaggi pubblicati
            msg = await publish_announcement(client, uid, info, POINTER_MESSAGE_IDS)
            ann_media_ids = []
            if "last_ann_media_ids" in info:
                ann_media_ids = info["last_ann_media_ids"]
            else:
                ann_media_ids = [msg.id] if msg else []
            # Invia una nuova preview privata con ID e bottoni, salva tutti gli id
            from modules.user_announcements_interactions.announcement_compiler import build_announcement_text
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
                f"ID annuncio: {msg.id}\n"
                f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
            )
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=f"delete_{','.join(str(i) for i in ann_media_ids)}_{','.join(str(i) for i in preview_with_ids)}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            confirm_msg = await client.send_message(uid, conferma, reply_markup=menu_btn)
            if confirm_msg:
                user_data[uid]["confirm_msg_id"] = confirm_msg.id
            # --- Cleanup dati utente dopo pubblicazione e preview con ID ---
            user_data.pop(uid, None)
        # --- Annullamento pubblicazione annuncio ---
        elif data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            info = user_data.get(uid, {})
            preview_id = info.get("preview_msg_id")
            confirm_id = info.get("confirm_msg_id")
            if preview_id:
                await safe_delete(client, uid, preview_id)
            if confirm_id:
                await safe_delete(client, uid, confirm_id)
            user_data.pop(uid, None)
            await send_main_menu(client, uid, "❌ Annuncio annullato. Sei tornato al menù principale.")
        # --- Eliminazione annuncio tramite bottone ---
        elif data.startswith("delete_"):
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
        # --- Torna alla domanda precedente ---
        elif data == "back_to_question":
            info = user_data[user_id]
            if info["step"] > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                for mid in info["messages_to_delete"]:
                    await safe_delete(client, user_id, mid)
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
            info = user_data[user_id]
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
                preview_id = await send_preview(client, user_id, info)
                user_data[user_id]["preview_msg_id"] = preview_id
                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                    [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(user_id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
                user_data[user_id]["confirm_msg_id"] = confirm_msg.id
        else:
            logging.warning(f"[BUTTONS] Callback non riconosciuta: {data} da utente {uid}")
            await callback_query.answer("❌ Azione non riconosciuta.", show_alert=True)
    except Exception as e:
        logging.exception(f"{YELLOW}Errore nel callback handler. Utente: {uid}, Data: {data}{RESET}")
        await send_clean_message(client, user_id, user_id, f"❌ Errore: {str(e)}")

