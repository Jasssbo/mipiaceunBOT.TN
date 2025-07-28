"""
Handler per tutte le interazioni con i bottoni InlineKeyboard.
"""
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import CATEGORY_QUESTIONS, user_data, bot, CHAT_ID, YELLOW, GREEN, RED, RESET
from modules.user_announcements_interactions.announcement_compiler import send_clean_message, send_preview, update_preview_with_id, publish_announcement, is_user_allowed_by_username, safe_delete
from source.modules.topic_guardian import is_user_allowed_by_username

from config import instance_client_bot
bot = instance_client_bot()
# ------------------------ BUTTONS CALLBACK HANDLER ------------------------
# buttons_callback_handler: Gestisce tutte le interazioni con i bottoni InlineKeyboard, 
# come la navigazione tra le domande, la conferma o l'annullamento della pubblicazione,
# e il ritorno al menù principale. Ogni blocco gestisce un tipo di callback specifico.
@bot.on_callback_query()
async def buttons_callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    try:
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            user_data[user_id].update({"category": cat, "step": 0, "answers": {}, "file": None, "file_type": None})
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
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
                [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
                [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
                [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
            ])
            await send_clean_message(client, user_id, user_id, "🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?", buttons)
        
        # --- Conferma pubblicazione annuncio ---
        elif data.startswith("confirm_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            info = user_data[uid]
            msg = await publish_announcement(client, uid, info)
            if msg:
                preview_id = info.get("preview_msg_id")
                if preview_id:
                    await update_preview_with_id(client, uid, preview_id, info, msg.id)
                await client.delete_messages(uid, callback_query.message.id)
                conferma = (
                    f"✅ Annuncio pubblicato!\n"
                    f"ID annuncio: {msg.id}\n"
                    f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
                )
                menu_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=f"delete_{msg.id}_{preview_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(uid, conferma, reply_markup=menu_btn)
                user_data[uid]["confirm_msg_id"] = confirm_msg.id
                
        # --- Annullamento pubblicazione annuncio ---
        elif data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            user = await client.get_users(uid)
            if not await is_user_allowed_by_username(client, user):
                await client.send_message(uid, "❌ Solo gli utenti presenti nel gruppo possono pubblicare. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
                return
            # Elimina i messaggi di preview e conferma
            info = user_data.get(uid, {})
            preview_id = info.get("preview_msg_id")
            confirm_id = info.get("confirm_msg_id")
            if preview_id:
                await safe_delete(client, uid, preview_id)
            if confirm_id:
                await safe_delete(client, uid, confirm_id)
            user_data.pop(uid, None)
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
                [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
                [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
                [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
            ])
            await send_clean_message(client, uid, uid, "❌ Annuncio annullato. Sei tornato al menù principale.", buttons)
       
        # --- Eliminazione annuncio tramite bottone ---
        elif data.startswith("delete_"):
            try:
                parts = data.split("_")
                ann_id = int(parts[1])
                preview_id = int(parts[2]) if len(parts) > 2 else None
                user = callback_query.from_user
                msg = await client.get_messages(CHAT_ID, ann_id)
                text = msg.text or msg.caption or ""
                author = f"@{user.username}" if user.username else user.first_name
                if author not in text:
                    await callback_query.answer("❌ Non sei l'autore di questo annuncio.", show_alert=True)
                    return
                await client.delete_messages(CHAT_ID, ann_id)
                # Elimina il messaggio di conferma pubblicazione (con bottone elimina)
                await client.delete_messages(user.id, callback_query.message.id)
                # Mostra conferma eliminazione con bottone torna al menù
                menu_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await client.send_message(
                    user.id,
                    f"✅ Annuncio eliminato con successo.\nID annuncio: {ann_id}",
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

    except Exception as e:
        logging.exception(f"{YELLOW}Errore nel callback handler.{RESET}")
        await send_clean_message(client, user_id, user_id, f"❌ Errore: {str(e)}")
