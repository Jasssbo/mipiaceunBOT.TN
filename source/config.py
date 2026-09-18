
"""
Configurazione delle variabili principali del bot.
Modifica questi valori per adattare il bot al tuo gruppo.
"""
import logging
import sys
import os
from dotenv import load_dotenv
from pyrogram import Client


# Caricamento variabili ambiente
load_dotenv("bot_infos.env")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "-1002461409137"))

# Lista degli admin (Telegram user IDs) — possono gestire segnalazioni e moderare
# Puoi aggiungere più admin separandoli con virgola nel .env: ADMIN_IDS=123456,789012
_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_str.split(",") if x.strip().isdigit()]

# Se mancano variabili obbligatorie, il bot si arresta per evitare errori futuri.
if not all([API_ID, API_HASH, BOT_TOKEN]):
    missing = [var for var in ["API_ID", "API_HASH", "BOT_TOKEN"] if not locals()[var]]
    logging.critical(f"Missing required .env variables: {', '.join(missing)}")
    sys.exit(1)

if not ADMIN_IDS:
    logging.warning("ADMIN_IDS non configurato. Nessun utente avrà accesso ai comandi admin. Aggiungi ADMIN_IDS al file .env")

 # Istanza del client Pyrogram
bot = Client("job_board_bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

# Costanti ANSI per log colorati
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"

# --- MESSAGGI DI PUNTAMENTO ---
# Definisce gli ID dei messaggi di puntamento per la pubblicazione degli annunci nei topic specifici.
POINTER_MESSAGE_IDS = {
    "job": 466,
    "project": 467,
    "event": 463,
    "profile": 468
}

# Definisci gli ID dei topic consentiti e NON consentiti per l'invio di messaggi
ALLOWED_TOPIC_IDS = [1]  # Sostituisci con gli ID dei topic dove gli utenti possono scrivere liberamente
NOT_ALLOWED_TOPIC_IDS = [10, 11, 12, 28]  # Sostituisci con gli ID dei topic dove SOLO il bot può pubblicare

# Mapping delle categorie per la visualizzazione nei log
CATEGORY_NAMES = {
    "job": "Annuncio di Lavoro",
    "project": "Progetto",
    "event": "Evento",
    "profile": "Profilo"
}

# Tempo entro cui l'utente deve finire l'annuncio altrimenti viene eliminato per alleggerire lo user_data
announce_timeout = 1200 # in secondi (20 minuti)

report_timeout = 300 # in secondi (5 minuti)

# --- RATE LIMITING ---
# Massimo numero di annunci per utente al giorno
MAX_ANNOUNCEMENTS_PER_DAY = 5
# Massimo numero di segnalazioni per utente al giorno
MAX_REPORTS_PER_DAY = 3

# --- RETENTION ---
# Durata di conservazione dei report in giorni (0 = nessuna scadenza)
REPORT_RETENTION_DAYS = 180  # 6 mesi

# --- INPUT LIMITS ---
# Lunghezza massima del testo per ogni campo dell'annuncio
MAX_INPUT_LENGTH = 2000

# --- AUTO-BAN ---
# Numero minimo di segnalazioni da utenti UNICI per attivare l'auto-ban
AUTO_BAN_THRESHOLD = 5

# --- DIZIONARIO DELLE DOMANDE ---
# Contiene le domande per ogni categoria di annuncio. Ogni domanda ha un'etichetta e un'opzione per essere saltata.
CATEGORY_QUESTIONS = {
    "job": [
        {"question": "💼 Scrivi qui il TITOLO LAVORATIVO che cerchi (es. Fonico):", "label": "💼 Titolo lavorativo richiesto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI LA MANSIONE e ciò di cui si dovrà occupare:", "label": "📜 Descrizione mansione:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📍 Scrivi qui il LUOGO in cui richiedi questa figura:", "label": "📍 Luogo del Lavoro:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💰 Scrivi qui il COMPENSO (opzionale):", "label": "💰 Compenso:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Come vuoi essere contattato? (es. @IlTuoNickTelegram). Puoi aggiungere telefono o email se vuoi, ma è opzionale — il tuo @username Telegram è sufficiente:", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "project": [
        {"question": "💡 Scrivi qui il TITOLO DEL PROGETTO:", "label": "💡 Titolo del Progetto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI IL TUO PROGETTO e spiega a quali ambiti è riferito:", "label": "📜 Descrizione del Progetto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "🖼️ Scrivi qui la LOCANDINA del PROGETTO (opzionale):", "label": "🖼️ Locandina:", "skippable": True, "allowed_types": ["photo"]},
        {"question": "🔗 Scrivi qui un LINK (opzionale):", "label": "🔗 Link:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📌 Puoi CARICARE UN FILE (opzionale):", "label": "📌 File allegato:", "skippable": True, "allowed_types": ["document"]},
        {"question": "📞 Come vuoi essere contattato? (es. @IlTuoNickTelegram). Puoi aggiungere telefono o email se vuoi, ma è opzionale — il tuo @username Telegram è sufficiente:", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "event": [
        {"question": "🎫 Scrivi qui il NOME DELL'EVENTO:", "label": "🎫 Nome evento:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📰 Inviami il VOLANTINO / FLYER dell'EVENTO (puoi inviare più foto, es. fronte e retro. Quando hai finito premi /done):",
            "label": "📰 Flyer:","skippable": True, "multi_file": True, "allowed_types": ["photo"]},
        {"question": "📍 Scrivi qui il LUOGO:", "label": "📍 Luogo:", "skippable": False, "allowed_types": ["text"]},
        {"question": "⏰ Scrivi qui la DATA E l'ORA dell'evento:", "label": "⏰ Data e ora:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💰 Scrivi qui il COSTO del BIGLIETTO (opzionale):", "label": "💰 Costo biglietto:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Come vuoi essere contattato? (es. @IlTuoNickTelegram). Puoi aggiungere telefono o email se vuoi, ma è opzionale — il tuo @username Telegram è sufficiente:", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "profile": [
        {"question": "👤 Scrivi qui il tuo NOME E COGNOME:", "label": "👤 Nome e cognome:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💼 Scrivi qui la tua PROFESSIONE:", "label": "💼 Professione:", "skippable": False, "allowed_types": ["text"]},
        {"question": "🖼️ Carica una tua FOTO o dei tuoi lavori (puoi inviare più foto, Quando hai finito premi /done):",
            "label": "🖼️ Foto/Lavori:","skippable": True, "multi_file": True, "allowed_types": ["photo"]},
        {"question": "📝 Scrivi una tua breve BIOGRAFIA (opzionale):", "label": "📝 Bio.:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI brevemente le competenze (max. 5 righe):", "label": "📜 Competenze:", "skippable": False, "allowed_types": ["text"]},
        {"question": "🔗 LINK al tuo Profilo LinkedIn (opzionale):", "label": "🔗 LinkedIn:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Come vuoi essere contattato? (es. @IlTuoNickTelegram). Puoi aggiungere telefono o email se vuoi, ma è opzionale — il tuo @username Telegram è sufficiente:", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ]
}


