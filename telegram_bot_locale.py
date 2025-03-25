from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
import os
import sys
import logging
from dotenv import load_dotenv

# Configura il logging (sia su file che in console)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
       #logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger().setLevel(logging.DEBUG)

# ------------------------------
# CONFIGURAZIONE DEL BOT
# ------------------------------
load_dotenv("bot_infos.env")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = int(os.getenv("CHAT_ID"))

if not all([API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, CHAT_ID]):
    logging.error("Errore: alcune variabili di ambiente non sono state caricate correttamente.")
    exit(1)

# I messaggi pointer (da creare manualmente su Telegram) – NON FISSATI, sono solo riferimenti
POINTER_MESSAGE_IDS = {
    "job": 466,       # Inserisci il vero message_id per "job"
    "collab": 468,    # Inserisci il vero message_id per "collab"
    "event": 463,     # Inserisci il vero message_id per "event"
    "project": 467    # Inserisci il vero message_id per "project"
}

CATEGORY_QUESTIONS = {
    "job": [
        "📝 Titolo richiesto:",
        "📜 Descrizione del lavoro:",
        "📍 Luogo:",
        "📞 Contatti (email o Telegram):"
    ],
    "collab": [
        "🔖 Chi si propone?",
        "📜 C.V.:",
        "💼 LinkedIn (opzionale):",
        "📞 Contatti (email o Telegram):"
    ],
    "event": [
        "📅 Nome dell'evento:",
        "📜 Descrizione dell'evento:",
        "Volantino / Flyer (opzionale):",
        "📍 Luogo:",
        "📆 Data e ora:",
        "💰 Entrata:",
        "📞 Contatti (email o Telegram):"
    ],
    "project": [
        "🚀 Titolo del progetto:",
        "📜 Descrizione del progetto:",
        "🔗 Link (opzionale):",
        "📎 Puoi caricare un file (opzionale):",
        "📞 Contatti (email o Telegram):"
    ]
}

# Dizionario globale per memorizzare temporaneamente i dati degli utenti
user_data = {}

# ------------------------------
# INIZIALIZZAZIONE DEL BOT
# ------------------------------
bot = Client("job_board_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ------------------------------
# HANDLER /start
# ------------------------------
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    try:
        if len(message.command) > 1:
            param = message.command[1]
            if param.startswith("new_"):
                category = param.replace("new_", "")
                if category not in POINTER_MESSAGE_IDS:
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return
                # Avvia il flusso per la categoria scelta
                user_data[message.from_user.id] = {"category": category, "step": 0, "answers": {}}
                await message.reply_text(CATEGORY_QUESTIONS[category][0])
                return

        # Se non viene passato nessun parametro, mostra un menu principale
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Pubblica Annuncio", url=f"https://t.me/{BOT_USERNAME}?start=new_job")],
            [InlineKeyboardButton("🤝 Offri Collaborazione", url=f"https://t.me/{BOT_USERNAME}?start=new_collab")],
            [InlineKeyboardButton("📆 Organizza Evento", url=f"https://t.me/{BOT_USERNAME}?start=new_event")],
            [InlineKeyboardButton("🚀 Proponi Progetto", url=f"https://t.me/{BOT_USERNAME}?start=new_project")]
        ])
        await message.reply_text("👋 **Benvenuto!**\nScegli cosa vuoi fare:", reply_markup=buttons)
    except Exception as e:
        logging.error(f"Errore nel comando /start: {str(e)}")

# ------------------------------
# HANDLER PER LA RACCOLTA DEI DATI DELL'ANNUNCIO
# ------------------------------
@bot.on_message(filters.private)
async def collect_data_handler(client, message: Message):
    try:
        user_id = message.from_user.id
        if user_id not in user_data:
            return

        user_info = user_data[user_id]
        category = user_info["category"]
        step = user_info["step"]
        current_question = CATEGORY_QUESTIONS[category][step]

        # Gestione dei file (immagini o documenti)
        if message.photo:
            file_id = message.photo.file_id
            user_info["answers"][current_question] = "🖼 Immagine allegata."
            user_info["file"] = file_id
            user_info["file_type"] = "photo"
        elif message.document:
            file_id = message.document.file_id
            user_info["answers"][current_question] = "📎 Documento allegato."
            user_info["file"] = file_id
            user_info["file_type"] = "document"
        # Gestione del testo
        elif message.text and message.text.strip():
            # Se il campo è opzionale e l'utente invia "/skip", saltiamo il campo
            if "(opzionale)" in current_question and message.text.strip().lower() == "/skip":
                # Non aggiungiamo il campo alle risposte
                pass
            else:
                user_info["answers"][current_question] = message.text.strip()
        else:
            await message.reply_text("⚠️ Il messaggio non può essere vuoto. Riprova.")
            return

        step += 1
        if step < len(CATEGORY_QUESTIONS[category]):
            user_info["step"] = step
            await message.reply_text(CATEGORY_QUESTIONS[category][step])
        else:
            await send_preview(client, user_id)
    except Exception as e:
        logging.error(f"Errore nella raccolta dei dati: {str(e)}")
        await message.reply_text("❌ Si è verificato un errore, riprova più tardi.")

# ------------------------------
# INVIO DELL'ANTEPRIMA DELL'ANNUNCIO
# ------------------------------
async def send_preview(client, user_id):
    try:
        user_info = user_data[user_id]
        # Creiamo il messaggio solo con i campi compilati
        message_text = "\n".join([f"🔹 **{key}** {value}" for key, value in user_info["answers"].items()])
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
            [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")]
        ])

        if "file" in user_info:
            if user_info.get("file_type") == "photo":
                await client.send_photo(user_id, user_info["file"], caption=message_text, reply_markup=buttons)
            else:
                await client.send_document(user_id, user_info["file"], caption=message_text, reply_markup=buttons)
        else:
            await client.send_message(user_id, text=f"📌 **Anteprima Annuncio:**\n\n{message_text}", reply_markup=buttons)
    except Exception as e:
        logging.error(f"Errore in send_preview: {str(e)}")

# ------------------------------
# HANDLER PER I CALLBACK (CONFERMA/ANNULLA)
# ------------------------------
@bot.on_callback_query(filters.regex("^(confirm|cancel)_"))
async def confirmation_handler(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        user_id = int(data.split("_")[1])
        if data.startswith("confirm_"):
            await publish_announcement(client, user_id)
            await callback_query.message.edit_text("✅ Annuncio pubblicato con successo!")
        elif data.startswith("cancel_"):
            if user_id in user_data:
                del user_data[user_id]
            await callback_query.message.edit_text("❌ Annuncio annullato. Puoi crearne un altro con /start.")
    except Exception as e:
        logging.error(f"Errore in confirmation_handler: {str(e)}")

# ------------------------------
# PUBBLICAZIONE DELL'ANNUNCIO
# ------------------------------
async def publish_announcement(client, user_id):
    try:
        category = user_data[user_id]["category"]
        pointer_message_id = POINTER_MESSAGE_IDS.get(category)
        message_text = "\n".join([f"🔹 **{key}** {value}" for key, value in user_data[user_id]["answers"].items()])

        if "file" in user_data[user_id]:
            if user_data[user_id].get("file_type") == "photo":
                await client.send_photo(CHAT_ID, user_data[user_id]["file"],
                                        caption=message_text,
                                        reply_to_message_id=pointer_message_id)
            else:
                await client.send_document(CHAT_ID, user_data[user_id]["file"],
                                           caption=message_text,
                                           reply_to_message_id=pointer_message_id)
        else:
            await client.send_message(CHAT_ID,
                                      text=message_text,
                                      reply_to_message_id=pointer_message_id)

        del user_data[user_id]
    except Exception as e:
        logging.error(f"Errore in publish_announcement: {str(e)}")

# ------------------------------
# AVVIO DEL BOT
# ------------------------------
if __name__ == "__main__":
    bot.run()
