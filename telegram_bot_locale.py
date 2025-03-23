from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import os
from dotenv import load_dotenv
import logging

# Configurazione logging per debug
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Carica le variabili di ambiente dal file .env
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

# Dizionario per memorizzare i dati degli utenti in base alla categoria selezionata
user_data = {}

# Mapping tra categorie e ID dei topic
CATEGORY_TOPIC_IDS = {
    "job": 12,
    "collab": 10,
    "event": 11,
    "project": 28
}

CATEGORY_QUESTIONS = {
    "job": ["📝 Inserisci il titolo del lavoro:", "📜 Inserisci la descrizione:", "📍 Specifica la posizione:", "📞 Contatti (email o Telegram):"],
    "collab": ["🔖 Inserisci il titolo della collaborazione:", "📜 Descrivi il tipo di collaborazione:", "💰 Budget (opzionale):", "📞 Contatti (email o Telegram):"],
    "event": ["📅 Nome dell'evento:", "📜 Descrizione dell'evento:", "📍 Luogo dell'evento:", "📆 Data e ora:", "📞 Contatti (email o Telegram):"],
    "project": ["🚀 Titolo del progetto:", "📜 Descrizione del progetto:", "🔗 Link al progetto (opzionale):", "📎 Puoi caricare file (immagini, documenti, etc.):", "📞 Contatti (email o Telegram):"]
}

@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start_handler(client, message: Message):
    try:
        if len(message.command) > 1:
            param = message.command[1]
            
            if param.startswith("new_"):
                category = param.replace("new_", "")
                if category not in CATEGORY_TOPIC_IDS:
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return

                user_data[message.from_user.id] = {"category": category, "step": 0, "answers": {}}
                await message.reply_text(CATEGORY_QUESTIONS[category][0])
                return
            
            elif param.startswith("search_"):
                category = param.replace("search_", "")
                if category not in CATEGORY_TOPIC_IDS:
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return
                
                topic_id = CATEGORY_TOPIC_IDS[category]
                await message.reply_text(f"🔍 Cerca un annuncio in questa categoria. Invia una parola chiave:")
                
                async def search_handler(client, m):
                    if m.from_user.id != message.from_user.id:
                        return

                    keyword = m.text.lower()
                    results_found = False
                    try:
                        async for msg in client.search_messages(int(CHAT_ID), query=keyword, message_thread_id=topic_id):
                            results_found = True
                            await m.reply_text(f"🔎 **Annuncio trovato:**\n\n{msg.text}")
                    except Exception as e:
                        await m.reply_text("⚠️ Errore durante la ricerca.")

                    if not results_found:
                        await m.reply_text("⚠️ Nessun annuncio trovato.")
                    
                    app.remove_handler(search_handler, group=1)

                app.add_handler(filters.text & filters.private, search_handler, group=1)
                return
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Pubblica Annuncio", url=f"https://t.me/{BOT_USERNAME}?start=new_job")],
            [InlineKeyboardButton("🤝 Offri una Collaborazione", url=f"https://t.me/{BOT_USERNAME}?start=new_collab")],
            [InlineKeyboardButton("📆 Organizza un Evento", url=f"https://t.me/{BOT_USERNAME}?start=new_event")],
            [InlineKeyboardButton("🚀 Proponi un Progetto", url=f"https://t.me/{BOT_USERNAME}?start=new_project")],
            [InlineKeyboardButton("🔍 Cerca Annunci", url=f"https://t.me/{BOT_USERNAME}?start=search_job")],
        ])
        await message.reply_text("👋 **Benvenuto!**\nScegli cosa vuoi fare:", reply_markup=buttons)
    except Exception as e:
        logging.error(f"Errore: {str(e)}")

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

async def publish_announcement(client, user_id):
    try:
        user_info = user_data[user_id]
        category = user_info["category"]
        topic_id = CATEGORY_TOPIC_IDS[category]

        contact = user_info["answers"].get("📞 Contatti (email o Telegram):", "")
        contact_text = f"📩 **Contatti:** {contact}" if "@" in contact and "." in contact else f"🚀 **Contatta qui:** @{contact}"

        message_text = "\n".join([f"🔹 **{key}** {value}" for key, value in user_info["answers"].items() if key != "📎 Puoi caricare file (immagini, documenti, etc.):"]) + f"\n{contact_text}"

        buttons = [[InlineKeyboardButton("📩 Contatta", url=f"https://t.me/{contact}")]] if "@" not in contact else []

        if "file" in user_info["answers"]:
            await client.send_document(chat_id=int(CHAT_ID), message_thread_id=topic_id, document=user_info["answers"]["file"], caption=message_text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await client.send_message(chat_id=int(CHAT_ID), message_thread_id=topic_id, text=message_text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logging.error(f"Errore: {str(e)}")

app.run()
