from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import os
from dotenv import load_dotenv
import logging

# Configurazione logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Carica le variabili di ambiente
load_dotenv("bot_infos.env")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = os.getenv("CHAT_ID")

if not all([API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, CHAT_ID]):
    print("Errore: alcune variabili di ambiente non sono state caricate correttamente.")
    exit(1)

app = Client("job_board_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}

# ID dei messaggi pointer (NON FISSATI, SOLO RIFERIMENTI)
POINTER_MESSAGE_IDS = {
    "job": 466,      # Inserisci l'ID reale del messaggio pointer per "job"
    "collab": 468,   # Inserisci l'ID reale del messaggio pointer per "collab"
    "event": 463,    # Inserisci l'ID reale del messaggio pointer per "event"
    "project": 467   # Inserisci l'ID reale del messaggio pointer per "project"
}

CATEGORY_QUESTIONS = {
    "job": [
        "📝 Inserisci il titolo:", 
        "📜 Inserisci la descrizione:",
        "📍 Specifica la posizione:",
        "📞 Contatti (email o Telegram):"],
    "collab": [
        "🔖 Titolo della collaborazione:",
        "📜 Tipo di collaborazione:",
        "💰 Budget (opzionale):",
        "📞 Contatti (email o Telegram):"],
    "event": [
        "📅 Nome dell'evento:",
        "📜 Descrizione dell'evento:",
        "📍 Luogo:",
        "📆 Data e ora:",
        "📞 Contatti (email o Telegram):"],
    "project": ["🚀 Titolo del progetto:", "📜 Descrizione del progetto:", "🔗 Link (opzionale):", "📎 Puoi caricare file (immagini, documenti, etc.):", "📞 Contatti (email o Telegram):"]
}

# ------------------------------
# HANDLER /start
# ------------------------------
@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start_handler(client, message: Message):
    try:
        if len(message.command) > 1:
            param = message.command[1]

            if param.startswith("new_"):
                category = param.replace("new_", "")
                if category not in POINTER_MESSAGE_IDS:
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return

                user_data[message.from_user.id] = {"category": category, "step": 0, "answers": {}}
                await message.reply_text(CATEGORY_QUESTIONS[category][0])
                return
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Pubblica Annuncio", url=f"https://t.me/{BOT_USERNAME}?start=new_job")],
            [InlineKeyboardButton("🤝 Offri Collaborazione", url=f"https://t.me/{BOT_USERNAME}?start=new_collab")],
            [InlineKeyboardButton("📆 Organizza Evento", url=f"https://t.me/{BOT_USERNAME}?start=new_event")],
            [InlineKeyboardButton("🚀 Proponi Progetto", url=f"https://t.me/{BOT_USERNAME}?start=new_project")],
            [InlineKeyboardButton("🔍 Cerca Annunci", url=f"https://t.me/{BOT_USERNAME}?start=search_job")],
        ])
        await message.reply_text("👋 **Benvenuto!**\nScegli cosa vuoi fare:", reply_markup=buttons)
    except Exception as e:
        logging.error(f"Errore: {str(e)}")

# ------------------------------
# GESTIONE INSERIMENTO ANNUNCIO
# ------------------------------
@app.on_message(filters.private)
async def collect_data_handler(client, message: Message):
    try:
        user_id = message.from_user.id
        if user_id not in user_data:
            return

        user_info = user_data[user_id]
        category = user_info["category"]
        step = user_info["step"]
        
        if category == "project" and step == 3 and message.document:
            file_info = await client.get_messages(user_id, message.message_id)
            user_info["answers"]["file"] = file_info.document.file_id
        else:
            user_info["answers"][CATEGORY_QUESTIONS[category][step]] = message.text

        step += 1
        if step < len(CATEGORY_QUESTIONS[category]):
            user_info["step"] = step
            await message.reply_text(CATEGORY_QUESTIONS[category][step])
        else:
            await publish_announcement(client, user_id)
            del user_data[user_id]
    except Exception as e:
        logging.error(f"Errore: {str(e)}")

# ------------------------------
# PUBBLICAZIONE ANNUNCIO NEL TOPIC GIUSTO (SENZA message_thread_id)
# ------------------------------
async def publish_announcement(client, user_id):
    """Pubblica l'annuncio rispondendo al messaggio pointer del topic corretto."""
    try:
        category = user_data[user_id]["category"]
        chat_id = int(CHAT_ID)
        pointer_message_id = POINTER_MESSAGE_IDS.get(category)

        if not pointer_message_id:
            await client.send_message(user_id, "⚠️ Errore: Nessun messaggio pointer trovato per questa categoria.")
            return

        message_text = "\n".join([f"🔹 **{key}** {value}" for key, value in user_data[user_id]["answers"].items()])
        
        await client.send_message(
            chat_id=chat_id,
            reply_to_message_id=pointer_message_id,  # Risponde direttamente al messaggio pointer
            text=message_text
        )

        await client.send_message(user_id, "✅ Il tuo annuncio è stato pubblicato con successo!")
    except Exception as e:
        logging.error(f"Errore: {str(e)}")
        await client.send_message(user_id, "❌ Si è verificato un errore durante la pubblicazione dell'annuncio.")

# Avvia il bot
app.run()
