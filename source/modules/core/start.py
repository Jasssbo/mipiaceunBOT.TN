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

sessions = get_announcement_sessions()

from middleware.permissions import require_group_member

@bot.on_message(filters.command("start") & filters.private)
@require_group_member
async def start_handler(client, message: Message):
    user = message.from_user
    username = user.username if user.username else user.first_name
    logging.info(f"[START] L'Utente @{username} ha avviato una conversazione con il bot")
    
    # Check if the user is an adult and accepts terms
    # For now, we will show a consent message with inline buttons
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    consent_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Dichiaro di avere 18+ anni e accetto i Termini", callback_data="accept_terms")],
        [InlineKeyboardButton("📜 Leggi Termini", callback_data="read_terms"), InlineKeyboardButton("🔒 Privacy", callback_data="read_privacy")]
    ])
    
    welcome_text = (
        "👋 **Benvenuto su mipiaceunBOT!**\n\n"
        "Questo bot ti permette di pubblicare annunci per trovare lavoro, "
        "condividere progetti o eventi nella nostra community.\n\n"
        "⚠️ **Prima di iniziare:**\n"
        "• Devi avere **almeno 18 anni** per utilizzare questo servizio.\n"
        "• Utilizzando il bot accetti i nostri Termini di Servizio e l'Informativa sulla Privacy.\n\n"
        "Per favore, conferma di avere i requisiti e di accettare le condizioni per continuare."
    )
    
    await send_clean_message(client, user.id, message.chat.id, welcome_text, consent_keyboard)



