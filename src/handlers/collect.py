import logging
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from utils.state import user_data
from utils.helpers import send_clean_message, send_preview
from questions import CATEGORY_QUESTIONS


def register(app):
    @app.on_message(filters.private & ~filters.command("start"))
    async def collect_data_handler(client, message: Message):
        uid = message.from_user.id
        if uid not in user_data:
            return

        try:
            info = user_data[uid]
            cat, step = info["category"], info["step"]
            q_data = CATEGORY_QUESTIONS[cat][step]
            label = q_data["label"]

            if message.photo or message.document:
                info["answers"][label] = "📎 File allegato."
                info["file"] = message.photo.file_id if message.photo else message.document.file_id
                info["file_type"] = "photo" if message.photo else "document"
            elif message.text:
                if q_data.get("skippable") and message.text.lower().strip() == "/skip":
                    info["answers"][label] = "Saltato."
                else:
                    info["answers"][label] = message.text.strip()

            info["step"] += 1

            # next question
            if info["step"] < len(CATEGORY_QUESTIONS[cat]):
                nxt = CATEGORY_QUESTIONS[cat][info["step"]]
                buttons = [[InlineKeyboardButton("⬅️ Torna alla domanda precedente",
                                                 callback_data="back_to_question")]]
                if nxt.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda",
                                                            callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù",
                                                     callback_data="back_to_menu")])

                await send_clean_message(client, uid, message.chat.id,
                                         nxt["question"], InlineKeyboardMarkup(buttons))
            else:
                # preview without ID
                preview_id = await send_preview(client, uid, info)
                info["preview_msg_id"] = preview_id

                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ Conferma", callback_data=f"confirm_{uid}")],
                    [InlineKeyboardButton(
                        "❌ Annulla", callback_data=f"cancel_{uid}")],
                    [InlineKeyboardButton(
                        "🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                cmsg = await client.send_message(uid,
                                                 "✅ Confermi di voler pubblicare questo annuncio?",
                                                 reply_markup=confirm_btns)
                info["confirm_msg_id"] = cmsg.id
        except Exception:
            logging.exception("Errore nella raccolta dati")
