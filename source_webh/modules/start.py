"""
Handler per il comando /start (versione webhook).
Verifica la presenza dell'utente nel gruppo e mostra il menù principale.
"""
import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import GREEN, RED, YELLOW, RESET, bot, get_user_data, set_user_data
from modules.user_announcements_interactions.announcement_compiler import send_clean_message, is_user_allowed_by_username

# --- Handler per comando /start: verifica presenza utente nel gruppo e mostra menù principale ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    """
    Handler per comando /start.
    In versione webhook: carica/salva user_data da Redis invece della memoria.
    """
    user = message.from_user
    username = user.username if user.username else user.first_name
    presente = await is_user_allowed_by_username(client, user)
    
    # Log dell'accesso
    logging.info(f"[START] Utente {username} ha avviato il bot. Presente nel gruppo: {presente}")
    
    if not presente:
        await message.reply("❌  Solo gli utenti presenti nel gruppo possono usare il bot. Assicurati di avere un @username pubblico (nel tuo profilo) e di essere nel gruppo (https://t.me/mipiaceunBOTTN).")
        return
    
    # Inizializza user_data in Redis (sostituisce user_data[user.id] = {...})
    user_session = {
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
    
    # Salva in Redis invece della memoria
    if not set_user_data(user.id, user_session):
        logging.error(f"[START] Failed to save user session for {user.id}")
        await message.reply("❌ Errore interno. Riprova più tardi.")
        return
    
    # Crea keyboard del menu principale
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")],
        [InlineKeyboardButton("🚨 Segnala utente", callback_data="report_user")]
    ])
    
    await send_clean_message(client, user.id, message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)