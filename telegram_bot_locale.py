from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
from dotenv import load_dotenv
import logging
import asyncio

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Carica le variabili di ambiente dal file .env (o dal file che usi, ad es. bot_infos.env)
load_dotenv()

# CONFIGURAZIONE API TELEGRAM tramite .env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = os.getenv("CHAT_ID")

app = Client("job_board_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dizionario per salvare temporaneamente i dati inseriti dagli utenti
user_data = {}

# Mapping tra le categorie e gli ID dei topic (per pubblicazione e ricerca)
CATEGORY_TOPIC_IDS = {
    "job": 12,      # Annunci Lavorativi (Topic ID 12)
    "collab": 10,   # Offro Collaborazioni (Topic ID 10)
    "event": 11,    # Eventi & Workshop (Topic ID 11)
    "project": 28   # Progetti & Teamwork (Topic ID 28)
}

# Mapping per i nomi dei topic (utile per i messaggi all'utente)
CATEGORY_TOPIC_NAMES = {
    "job": "Annunci Lavorativi",
    "collab": "Offro Collaborazioni",
    "event": "Eventi & Workshop",
    "project": "Progetti & Teamwork"
}

# Timeout di inattività in secondi
# Per ora impostato a 5 minuti (300 secondi); in futuro potrai modificarlo
INACTIVITY_TIMEOUT = 5 * 60

# Variabile globale per il task di inattività
inactivity_timer = None

# Funzione che ferma il bot dopo un periodo di inattività
async def stop_bot_after_timeout():
    await asyncio.sleep(INACTIVITY_TIMEOUT)
    print("⏰ Timeout di inattività raggiunto. Spegnimento del bot...")
    await app.stop()

# Funzione per resettare il timer di inattività (chiamata ad ogni input)
def reset_inactivity_timer():
    global inactivity_timer
    if inactivity_timer is not None:
        inactivity_timer.cancel()
    inactivity_timer = asyncio.create_task(stop_bot_after_timeout())

# Inizializza il timer all'avvio
reset_inactivity_timer()

# -------------------------------------
# Handler per il comando /start in chat privata.
# Gestisce sia il menu principale che le interazioni via deep linking.
# -------------------------------------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    reset_inactivity_timer()  # Reset del timer per ogni input

    # Se il comando /start ha un parametro (deep linking)
    if len(message.command) > 1:
        param = message.command[1]
        # Caso "new_": avvio della raccolta dati per pubblicare un annuncio.
        if param.startswith("new_"):
            category = param.replace("new_", "")
            user_data[message.from_user.id] = {"category": category, "step": "titolo"}
            await message.reply_text("📝 **Inserisci il titolo:**")
            return
        # Caso "search_": avvio del processo di ricerca.
        elif param.startswith("search_"):
            category = param.replace("search_", "")
            topic_id = CATEGORY_TOPIC_IDS.get(category)
            topic_name = CATEGORY_TOPIC_NAMES.get(category, "")
            if not topic_id:
                await message.reply_text("⚠️ Errore: il topic non esiste.")
                return
            await message.reply_text(f"🔍 **Cerca un annuncio in {topic_name}**\n\nInvia una parola chiave:")

            # Handler temporaneo per la query di ricerca, specifico per l'utente.
            @app.on_message(filters.text & filters.private)
            async def get_search_query(client, m):
                reset_inactivity_timer()  # Reset del timer per ogni input
                if m.from_user.id != message.from_user.id:
                    return
                keyword = m.text.lower()
                results_found = False
                async for msg in client.search_messages(CHAT_ID, query=keyword, message_thread_id=topic_id):
                    results_found = True
                    await m.reply_text(f"🔎 **Annuncio trovato:**\n\n{msg.text}")
                if not results_found:
                    await m.reply_text("⚠️ Nessun annuncio trovato per la parola chiave inserita.")
                await m.reply_text("🔍 **Fine dei risultati.**")
                # Rimuove l'handler per evitare conflitti futuri.
                app.remove_handler(get_search_query, group=0)
            return
        else:
            await message.reply_text("Comando non riconosciuto. Usa /start per vedere il menu.")
            return

    # Se non ci sono parametri, mostra il menu con pulsanti deep linking.
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Pubblica Annuncio Lavorativo", url=f"https://t.me/{BOT_USERNAME}?start=new_job")],
        [InlineKeyboardButton("🤝 Offri una Collaborazione", url=f"https://t.me/{BOT_USERNAME}?start=new_collab")],
        [InlineKeyboardButton("📆 Organizza un Evento", url=f"https://t.me/{BOT_USERNAME}?start=new_event")],
        [InlineKeyboardButton("🚀 Proponi un Progetto", url=f"https://t.me/{BOT_USERNAME}?start=new_project")],
        [InlineKeyboardButton("🔍 Cerca Annuncio Lavorativo", url=f"https://t.me/{BOT_USERNAME}?start=search_job")],
        [InlineKeyboardButton("🔍 Cerca Offri Collaborazioni", url=f"https://t.me/{BOT_USERNAME}?start=search_collab")],
        [InlineKeyboardButton("🔍 Cerca Eventi & Workshop", url=f"https://t.me/{BOT_USERNAME}?start=search_event")],
        [InlineKeyboardButton("🔍 Cerca Progetti & Teamwork", url=f"https://t.me/{BOT_USERNAME}?start=search_project")]
    ])
    await message.reply_text("👋 **Benvenuto!**\nScegli cosa vuoi fare:", reply_markup=buttons)

# -------------------------------------
# Handler per la raccolta dati per la pubblicazione.
# Si attiva se l'utente ha già avviato il flusso con /start new_<categoria>.
# -------------------------------------
@app.on_message(filters.private)
async def collect_data(client, message):
    reset_inactivity_timer()  # Reset del timer per ogni messaggio
    user_id = message.from_user.id
    if user_id not in user_data:
        return  # Ignora i messaggi che non fanno parte del flusso di pubblicazione

    step = user_data[user_id]["step"]
    # Definiamo la sequenza dei passi da seguire
    steps = {
        "titolo": "📌 Inserisci la descrizione:",
        "descrizione": "📍 Inserisci la posizione o il luogo:",
        "luogo": "📞 Inserisci i contatti (email o Telegram):",
        "contatti": None  # Ultimo step
    }
    # Salva la risposta dell'utente per il passo corrente
    user_data[user_id][step] = message.text

    # Determina se c'è un passo successivo
    next_steps = list(steps.keys())
    if step in next_steps and next_steps.index(step) < len(next_steps) - 1:
        next_step = next_steps[next_steps.index(step) + 1]
        user_data[user_id]["step"] = next_step
        await message.reply_text(steps[next_step])
    else:
        # Se tutti i dati sono stati raccolti, pubblica l'annuncio
        await publish_announcement(client, user_id)
        del user_data[user_id]

# -------------------------------------
# Funzione per pubblicare l'annuncio nel topic corretto del gruppo.
# Utilizza il CHAT_ID del gruppo e il topic_id specifico per la categoria.
# -------------------------------------
async def publish_announcement(client, user_id):
    reset_inactivity_timer()  # Reset del timer per sicurezza
    category = user_data[user_id]["category"]
    topic_id = CATEGORY_TOPIC_IDS.get(category)
    if not topic_id:
        await client.send_message(user_id, "⚠️ Errore: il topic non esiste.")
        return

    message_text = f"""
🔹 **Titolo:** {user_data[user_id]['titolo']}
📜 **Descrizione:** {user_data[user_id]['descrizione']}
📍 **Luogo:** {user_data[user_id]['luogo']}
📞 **Contatti:** {user_data[user_id]['contatti']}

🚀 **Candidati o scopri di più premendo il pulsante qui sotto!**
"""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contatta", url=f"https://t.me/{user_data[user_id]['contatti']}")]
    ])

    # Pubblica l'annuncio nel thread specifico del gruppo (CHAT_ID + topic_id)
    await client.send_message(chat_id=CHAT_ID, message_thread_id=topic_id, text=message_text, reply_markup=buttons)

# -------------------------------------
# Avvio del bot
# -------------------------------------
app.run()
