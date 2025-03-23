from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
from dotenv import load_dotenv
import logging

# Configurazione logging per debug
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Carica le variabili di ambiente dal file .env
load_dotenv("bot_infos.env")

# Configurazione API TELEGRAM
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = os.getenv("CHAT_ID")

# Verifica se le variabili di ambiente sono state caricate correttamente
if not all([API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, CHAT_ID]):
    print("Errore: alcune variabili di ambiente non sono state caricate correttamente.")
    exit(1)

# Inizializza il client Pyrogram
try:
    app = Client("job_board_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    print("Client Pyrogram inizializzato correttamente.")
except Exception as e:
    print(f"Errore: impossibile inizializzare il client Pyrogram. {str(e)}")
    exit(1)

# Dizionario per salvare temporaneamente i dati degli utenti
user_data = {}

# Mapping tra categorie e ID dei topic
CATEGORY_TOPIC_IDS = {
    "job": 12,
    "collab": 10,
    "event": 11,
    "project": 28
}

CATEGORY_TOPIC_NAMES = {
    "job": "Annunci Lavorativi",
    "collab": "Offro Collaborazioni",
    "event": "Eventi & Workshop",
    "project": "Progetti & Teamwork"
}

print("Dizionari CATEGORY_TOPIC_IDS e CATEGORY_TOPIC_NAMES creati correttamente.")

# -------------------------------------
# HANDLER /start (menu principale e deep linking)
# -------------------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    try:
        print(f"Ricevuto comando /start da {message.from_user.id}.")
        if len(message.command) > 1:
            param = message.command[1]
            print(f"Parametro: {param}")

            # Flusso per pubblicazione annuncio
            if param.startswith("new_"):
                category = param.replace("new_", "")
                print(f"Categoria: {category}")
                if category not in CATEGORY_TOPIC_IDS:
                    print("Errore: categoria non valida.")
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return

                user_data[message.from_user.id] = {"category": category, "step": "titolo"}
                print(f"Dati utente aggiornati: {user_data[message.from_user.id]}")
                await message.reply_text("📝 **Inserisci il titolo:**")
                return
            
            # Flusso per ricerca annunci
            elif param.startswith("search_"):
                category = param.replace("search_", "")
                print(f"Categoria: {category}")
                if category not in CATEGORY_TOPIC_IDS:
                    print("Errore: categoria non valida.")
                    await message.reply_text("⚠️ Errore: categoria non valida.")
                    return

                topic_id = CATEGORY_TOPIC_IDS.get(category)
                topic_name = CATEGORY_TOPIC_NAMES.get(category, "")
                print(f"ID topic: {topic_id}, nome topic: {topic_name}")

                await message.reply_text(f"🔍 **Cerca un annuncio in {topic_name}**\n\nInvia una parola chiave:")

                # Funzione di ricerca temporanea
                async def get_search_query(client, m):
                    print(f"Ricevuto messaggio di ricerca da {m.from_user.id}.")
                    if m.from_user.id != message.from_user.id:
                        print("Errore: utente non autorizzato.")
                        return

                    keyword = m.text.lower()
                    print(f"Parola chiave: {keyword}")
                    results_found = False
                    try:
                        async for msg in client.search_messages(int(CHAT_ID), query=keyword, message_thread_id=topic_id):
                            results_found = True
                            print(f"Risultato trovato: {msg.text}")
                            await m.reply_text(f"🔎 **Annuncio trovato:**\n\n{msg.text}")
                    except Exception as e:
                        print(f"Errore: impossibile eseguire la ricerca. {str(e)}")
                        await m.reply_text("⚠️ Errore: impossibile eseguire la ricerca.")

                    if not results_found:
                        print("Nessun risultato trovato.")
                        await m.reply_text("⚠️ Nessun annuncio trovato.")

                    await m.reply_text("🔍 **Fine dei risultati.**")
                    app.remove_handler(get_search_query, group=1)  # Rimuove l'handler dopo la ricerca

                app.add_handler(filters.text & filters.private, get_search_query, group=1)
                return

            else:
                print("Comando non riconosciuto.")
                await message.reply_text("Comando non riconosciuto. Usa /start per il menu.")
                return

        # Se nessun parametro, mostra il menu principale
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Pubblica Annuncio", url=f"https://t.me/{BOT_USERNAME}?start=new_job")],
            [InlineKeyboardButton("🤝 Offri una Collaborazione", url=f"https://t.me/{BOT_USERNAME}?start=new_collab")],
            [InlineKeyboardButton("📆 Organizza un Evento", url=f"https://t.me/{BOT_USERNAME}?start=new_event")],
            [InlineKeyboardButton("🚀 Proponi un Progetto", url=f"https://t.me/{BOT_USERNAME}?start=new_project")],
            [InlineKeyboardButton("🔍 Cerca Annunci", url=f"https://t.me/{BOT_USERNAME}?start=search_job")],
        ])
        await message.reply_text("👋 **Benvenuto!**\nScegli cosa vuoi fare:", reply_markup=buttons)
    except Exception as e:
        print(f"Errore: impossibile gestire il comando /start. {str(e)}")

# -------------------------------------
# RACCOLTA DATI PER PUBBLICAZIONE ANNUNCIO
# -------------------------------------
@app.on_message(filters.private)
async def collect_data_handler(client, message):
    try:
        print(f"Ricevuto messaggio da {message.from_user.id}.")
        user_id = message.from_user.id
        if user_id not in user_data:
            print("Errore: utente non autorizzato.")
            return  # Ignora messaggi non appartenenti al flusso

        step = user_data[user_id]["step"]
        print(f"Passo corrente: {step}")
        steps = {
            "titolo": "📌 Inserisci la descrizione:",
            "descrizione": "📍 Inserisci la posizione:",
            "luogo": "📞 Inserisci i contatti (email o Telegram):",
            "contatti": None  # Ultimo step
        }

        # Salva la risposta dell'utente per il passo corrente
        user_data[user_id][step] = message.text
        print(f"Dati utente aggiornati: {user_data[user_id]}")

        next_steps = list(steps.keys())
        if step in next_steps and next_steps.index(step) < len(next_steps) - 1:
            next_step = next_steps[next_steps.index(step) + 1]
            user_data[user_id]["step"] = next_step
            print(f"Passo successivo: {next_step}")
            await message.reply_text(steps[next_step])
        else:
            print("Pubblicazione annuncio completata.")
            await publish_announcement(client, user_id)
            del user_data[user_id]
    except Exception as e:
        print(f"Errore: impossibile raccogliere i dati per la pubblicazione dell'annuncio. {str(e)}")

# -------------------------------------
# PUBBLICAZIONE ANNUNCIO NEL GRUPPO
# -------------------------------------
async def publish_announcement(client, user_id):
    try:
        print(f"Pubblicazione annuncio per {user_id}.")
        category = user_data[user_id]["category"]
        print(f"Categoria: {category}")
        topic_id = CATEGORY_TOPIC_IDS.get(category)
        print(f"ID topic: {topic_id}")

        if not topic_id:
            print("Errore: topic non esistente.")
            await client.send_message(user_id, "⚠️ Errore: il topic non esiste.")
            return

        # Validazione contatti (email vs username Telegram)
        contact = user_data[user_id]['contatti']
        print(f"Contatti: {contact}")
        if "@" in contact and "." in contact:
            contact_text = f"📩 **Contatti:** {contact}"
            button = []
        else:
            contact_text = "🚀 **Candidati o scopri di più premendo il pulsante qui sotto!**"
            button = [[InlineKeyboardButton("📩 Contatta", url=f"https://t.me/{contact}")]]

        message_text = f"""
🔹 **Titolo:** {user_data[user_id]['titolo']}
📜 **Descrizione:** {user_data[user_id]['descrizione']}
📍 **Luogo:** {user_data[user_id]['luogo']}
{contact_text}
"""
        
        print(f"Testo del messaggio: {message_text}")
        await client.send_message(chat_id=int(CHAT_ID), message_thread_id=topic_id, text=message_text, reply_markup=InlineKeyboardMarkup(button))
    except Exception as e:
        print(f"Errore: impossibile pubblicare l'annuncio nel gruppo. {str(e)}")

# -------------------------------------
# AVVIO DEL BOT
# -------------------------------------
try:
    print("Avvio del bot...")
    app.run()
except Exception as e:
    print(f"Errore: impossibile avviare il bot. {str(e)}")
