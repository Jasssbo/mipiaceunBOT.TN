"""
Handler per il comando /start.
Verifica la presenza dell'utente nel gruppo e mostra il menù principale.
"""
import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import GREEN, RED, YELLOW, RESET, user_data, bot
from modules.user_announcements_interactions.announcement_compiler import send_clean_message, is_user_allowed_by_username

from config import instance_client_bot
bot = instance_client_bot()
# --- Handler per comando /start: verifica presenza utente nel gruppo e mostra menù principale ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user = message.from_user
    username = user.username if user.username else user.first_name
    presente = await is_user_allowed_by_username(client, user)
    logging.info(f"[START] Utente {username} ha avviato il bot. Presente nel gruppo: {presente}")
    if not presente:
        await message.reply("❌  Solo gli utenti presenti nel gruppo possono usare il bot. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
        return
    user_data[user.id] = {
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
    }
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
    ])
    await send_clean_message(client, user.id, message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)
