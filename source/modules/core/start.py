"""
Handler per il comando /start.
Verifica la presenza dell'utente nel gruppo e mostra il menù principale.
"""
import logging
from pyrogram import filters
from pyrogram.types import Message
from config import GREEN, RESET, bot
from modules.permissions.user_permissions import is_user_allowed_by_username
from modules.user_announcements_interactions.utils.message_utils import send_clean_message
from core.session_manager import get_announcement_sessions
from core.ui_components import build_main_menu_keyboard

# Get session manager
sessions = get_announcement_sessions()

# --- Handler per comando /start: verifica presenza utente nel gruppo e mostra menù principale ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user = message.from_user
    username = user.username if user.username else user.first_name
    presente = await is_user_allowed_by_username(client, user)
    if presente:
        logging.info(f"{GREEN}[START] L'Utente @{username} ha avviato una conversazione con il bot ed è PRESENTE nel gruppo: {presente} {RESET}")
    if not presente:
        await message.reply("❌  Solo gli utenti presenti nel gruppo possono usare il bot. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
        return
    
    # Initialize session for the user
    sessions.create_session(user.id, {
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
    await send_clean_message(client, user.id, message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)
