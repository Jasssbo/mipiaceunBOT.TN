"""
Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti.
"""
import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from source.config import GREEN, RED, YELLOW, RESET,CATEGORY_QUESTIONS, user_data
from modules.user_announcements_interactions.announcement_compiler import send_preview, send_clean_message
from source.config import bot

# ------------------------ RACCOLTA DATI UTENTE ------------------------
# --- Handler per la raccolta dati utente: gestisce domande, risposte e preview, eliminando i messaggi precedenti. ---
@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    user = message.from_user
    if user.id not in user_data:
        user_data[user.id] = {"user_messages_to_delete": []}
    if "user_messages_to_delete" not in user_data[user.id]:
        user_data[user.id]["user_messages_to_delete"] = []
    user_data[user.id]["user_messages_to_delete"].append(message.id)
    if user.id not in user_data:
        return
    try:
        info = user_data[user.id]
        cat = info["category"]
        step = info["step"]
        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]
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