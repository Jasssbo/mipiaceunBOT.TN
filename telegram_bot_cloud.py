# Bot Telegram per la gestione di una community online

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import time
import os
from dotenv import load_dotenv

# Carica le variabili di ambiente dal file .env
load_dotenv()

# CONFIGURAZIONE API TELEGRAM tramite .env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = int(os.getenv("CHAT_ID"))  # Assicurati che CHAT_ID sia un intero

app = Client("MultiFunctionBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# 🚀 MESSAGGIO DI BENVENUTO PRIVATO 🚀
WELCOME_MESSAGE = """👋 Benvenuto {first_name} nella nostra community! 🎨🚀

📌 **Ecco alcune informazioni importanti:**
- **Regole del gruppo:** [link alle regole]
- **Canale ufficiale:** @tuo_canale
- **Topic di discussione:** Fotografia, UX, Musica, etc.

Buona permanenza! 🚀
"""

@app.on_message(filters.new_chat_members)
async def welcome_new_users(client, message):
    """ Invia un messaggio di benvenuto privato ai nuovi membri del gruppo """
    for member in message.new_chat_members:
        await client.send_message(
            member.id, WELCOME_MESSAGE.format(first_name=member.first_name)
        )
        await message.reply(f"👋 {member.mention} è entrato nel gruppo! (Ha ricevuto il benvenuto in privato)")

# 🚨 ANTI-FLOOD 🚨
users_last_message = {}

@app.on_message(filters.group & filters.text)
async def anti_flood(client, message):
    """ Impedisce che un utente invii troppi messaggi in pochi secondi """
    user_id = message.from_user.id
    current_time = time.time()

    if user_id in users_last_message and current_time - users_last_message[user_id] < 3:
        await message.delete()
        await message.reply(f"⚠️ {message.from_user.mention}, non inviare messaggi troppo velocemente!", quote=True)
    users_last_message[user_id] = current_time

# 🚨 COMANDI DI MODERAZIONE 🚨
@app.on_message(filters.command("ban") & filters.group)
async def ban_user(client, message):
    """ Comando per bannare un utente """
    if not message.reply_to_message:
        await message.reply("❌ Rispondi a un messaggio per bannare un utente.")
        return

    user_id = message.reply_to_message.from_user.id
    await client.kick_chat_member(CHAT_ID, user_id)
    await message.reply(f"🚨 {message.reply_to_message.from_user.mention} è stato bannato.")

@app.on_message(filters.command("mute") & filters.group)
async def mute_user(client, message):
    """ Comando per mutare un utente """
    if not message.reply_to_message:
        await message.reply("❌ Rispondi a un messaggio per mutare un utente.")
        return

    user_id = message.reply_to_message.from_user.id
    await client.restrict_chat_member(CHAT_ID, user_id, permissions={"can_send_messages": False})
    await message.reply(f"🔇 {message.reply_to_message.from_user.mention} è stato mutato.")

# 📢 ANNUNCI FORMATTATI 📢
ANNOUNCE_TEMPLATE = """📢 **Nuova Opportunità di Lavoro!** 🎨🚀

🔹 **Titolo:** {title}
👤 **Richiesto da:** {user}
💼 **Tipo di lavoro:** {job_type}
📅 **Scadenza:** {deadline}
📍 **Luogo:** {location}
📞 **Contatto:** {contact}

📌 **Descrizione:**  
{description}

👉 Per candidarti, contatta **{contact}**!
"""

@app.on_message(filters.command("annuncio") & filters.private)
async def announce_request(client, message):
    """ Chiede agli utenti di inviare i dati per l'annuncio """
    await message.reply("📌 Invia il tuo annuncio nel seguente formato:\n\n"
                        "**Titolo:**\n**Tipo di lavoro:**\n**Scadenza:**\n**Luogo:**\n**Contatto:**\n**Descrizione:**")

@app.on_message(filters.text & filters.private)
async def process_announcement(client, message):
    """ Formatta e pubblica un annuncio nel gruppo """
    lines = message.text.split("\n")
    
    if len(lines) < 6:
        await message.reply("❌ Formato non valido! Segui il modello richiesto.")
        return
    
    data = {
        "title": lines[0].replace("Titolo:", "").strip(),
        "job_type": lines[1].replace("Tipo di lavoro:", "").strip(),
        "deadline": lines[2].replace("Scadenza:", "").strip(),
        "location": lines[3].replace("Luogo:", "").strip(),
        "contact": lines[4].replace("Contatto:", "").strip(),
        "description": "\n".join(lines[5:]).strip(),
        "user": message.from_user.mention
    }

    formatted_message = ANNOUNCE_TEMPLATE.format(**data)

    # Invia l'annuncio nel gruppo
    await client.send_message(CHAT_ID, formatted_message)
    await message.reply("✅ Il tuo annuncio è stato pubblicato!")

# Avvia il bot
app.run()
