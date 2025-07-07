from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import send_clean_message
from utils.state import user_data


def register(app):
    @app.on_message(filters.command("start") & filters.private)
    async def start_handler(client, message: Message):
        uid = message.from_user.id

        user_data[uid] = {
            "step": 0,
            "answers": {},
            "messages_to_delete": [],
            "last_bot_message_id": None,
            "file": None,
            "file_type": None,
            "category": None,
            "preview_msg_id": None,
            "confirm_msg_id": None
        }

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
            [InlineKeyboardButton("💼 Annuncio di Lavoro",
                                  callback_data="new_job")],
            [InlineKeyboardButton(
                "💡 Call Pubblica per un Progetto", callback_data="new_project")],
            [InlineKeyboardButton(
                "👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
        ])

        await send_clean_message(client, uid, message.chat.id,
                                 "Benvenuto! Cosa vuoi pubblicare all'interno della Community?",
                                 buttons)
