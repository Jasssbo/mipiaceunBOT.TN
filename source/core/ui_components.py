"""
Shared UI components to avoid circular dependencies.
Contains menu building functions and common UI elements.
"""
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")],
        [InlineKeyboardButton("🚨 Segnala utente", callback_data="report_user")]
    ])


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Build a simple 'back to menu' keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
    ])


def build_cancel_report_keyboard() -> InlineKeyboardMarkup:
    """Build cancel report keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Annulla segnalazione", callback_data="cancel_report")]
    ])
