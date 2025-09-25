"""
Configurazione webhook per il bot Telegram.
Sostituisce le variabili globali con chiamate al storage layer.
"""
import logging
import sys
import os
from dotenv import load_dotenv
from pyrogram import Client
from storage import init_storage, get_storage

# Caricamento variabili ambiente
# Su Render, le variabili vengono dal sistema, non da file .env
# Ma per sviluppo locale, proviamo a caricare il file se esiste
try:
    if os.path.exists("bot_infos_webh.env"):
        load_dotenv("bot_infos_webh.env")
        print("✅ Loaded local .env file")
except Exception as e:
    print(f"📝 Using system environment variables: {e}")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "-1002461409137"))

# Se mancano variabili obbligatorie, il bot si arresta per evitare errori futuri.
if not all([API_ID, API_HASH, BOT_TOKEN]):
    missing = [var for var in ["API_ID", "API_HASH", "BOT_TOKEN"] if not locals()[var]]
    logging.critical(f"Missing required .env variables: {', '.join(missing)}")
    sys.exit(1)

# Istanza del client Pyrogram
# Su Render, usa session in-memory per evitare "database is locked"
bot = Client(
    name=":memory:",  # Session in memoria, non su file
    api_id=int(API_ID), 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    in_memory=True  # Forza session in memoria
)

# Inizializza storage (Redis) all'avvio
try:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    storage = init_storage(redis_url)
    logging.info("Storage layer initialized successfully")
except Exception as e:
    logging.critical(f"Failed to initialize storage: {e}")
    sys.exit(1)

# Costanti ANSI per log colorati
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"

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

# Tempo entro cui l'utente deve finire l'annuncio altrimenti viene eliminato per alleggerire lo user_data
announce_timeout = 180  # in secondi

# --- WRAPPER FUNCTIONS per COMPATIBILITÀ ---
# Queste funzioni mantengono l'API originale ma usano Redis internamente

def get_user_data(user_id: int) -> dict:
    """Get user compilation data (compatibility wrapper)."""
    return get_storage().get_user_session(user_id) or {}

def set_user_data(user_id: int, data: dict) -> bool:
    """Set user compilation data (compatibility wrapper)."""
    return get_storage().set_user_session(user_id, data)

def delete_user_data(user_id: int) -> bool:
    """Delete user compilation data (compatibility wrapper)."""
    return get_storage().delete_user_session(user_id)

def get_report_state(user_id: int) -> dict:
    """Get user report state (compatibility wrapper)."""
    return get_storage().get_report_state(user_id) or {}

def set_report_state(user_id: int, data: dict) -> bool:
    """Set user report state (compatibility wrapper)."""
    return get_storage().set_report_state(user_id, data)

def delete_report_state(user_id: int) -> bool:
    """Delete user report state (compatibility wrapper)."""
    return get_storage().delete_report_state(user_id)

def is_user_in_timeout(user_id: int) -> bool:
    """Check if user is in announcement timeout (compatibility wrapper)."""
    return get_storage().is_user_in_timeout(user_id)

def set_user_timeout(user_id: int, timeout_datetime) -> bool:
    """Set user announcement timeout (compatibility wrapper)."""
    return get_storage().set_announce_timeout(user_id, timeout_datetime)

def delete_user_timeout(user_id: int) -> bool:
    """Delete user announcement timeout (compatibility wrapper)."""
    return get_storage().delete_announce_timeout(user_id)

# --- DIZIONARIO DELLE DOMANDE ---
# Contiene le domande per ogni categoria di annuncio. Ogni domanda ha un'etichetta e un'opzione per essere saltata.
CATEGORY_QUESTIONS = {
    "job": [
        {"question": "💼 Scrivi qui il TITOLO LAVORATIVO che cerchi (es. Fonico):", "label": "💼 Titolo lavorativo richiesto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI LA MANSIONE e ciò di cui si dovrà occupare:", "label": "📜 Descrizione mansione:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📍 Scrivi qui il LUOGO in cui richiedi questa figura:", "label": "📍 Luogo del Lavoro:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💰 Scrivi qui il COMPENSO (opzionale):", "label": "💰 Compenso:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Scrivi qui i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "project": [
        {"question": "💡 Scrivi qui il TITOLO DEL PROGETTO:", "label": "💡 Titolo del Progetto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI IL TUO PROGETTO e spiega a quali ambiti è riferito:", "label": "📜 Descrizione del Progetto:", "skippable": False, "allowed_types": ["text"]},
        {"question": "🖼️ Scrivi qui la LOCANDINA del PROGETTO (opzionale):", "label": "🖼️ Locandina:", "skippable": True, "allowed_types": ["photo"]},
        {"question": "🔗 Scrivi qui un LINK (opzionale):", "label": "🔗 Link:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📌 Puoi CARICARE UN FILE (opzionale):", "label": "📌 File allegato:", "skippable": True, "allowed_types": ["document"]},
        {"question": "📞 Scrivi qui i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "event": [
        {"question": "🎫 Scrivi qui il NOME DELL'EVENTO:", "label": "🎫 Nome evento:", "skippable": False, "allowed_types": ["text"]},
        {"question": "📰 Inviami il VOLANTINO / FLYER dell'EVENTO (puoi inviare più foto, es. fronte e retro. Quando hai finito premi /done):",
            "label": "📰 Flyer:","skippable": True, "multi_file": True, "allowed_types": ["photo"]},
        {"question": "📍 Scrivi qui il LUOGO:", "label": "📍 Luogo:", "skippable": False, "allowed_types": ["text"]},
        {"question": "⏰ Scrivi qui la DATA E l'ORA dell'evento:", "label": "⏰ Data e ora:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💰 Scrivi qui il COSTO del BIGLIETTO (opzionale):", "label": "💰 Costo biglietto:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Scrivi qui i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ],
    "profile": [
        {"question": "👤 Scrivi qui il tuo NOME E COGNOME:", "label": "👤 Nome e cognome:", "skippable": False, "allowed_types": ["text"]},
        {"question": "💼 Scrivi qui la tua PROFESSIONE:", "label": "💼 Professione:", "skippable": False, "allowed_types": ["text"]},
        {"question": "🖼️ Carica una tua FOTO o dei tuoi lavori (puoi inviare più foto, Quando hai finito premi /done):",
            "label": "🖼️ Foto/Lavori:","skippable": True, "multi_file": True, "allowed_types": ["photo"]},
        {"question": "📝 Scrivi una tua breve BIOGRAFIA (opzionale):", "label": "📝 Bio.:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📜 DESCRIVI brevemente le competenze (max. 5 righe):", "label": "📜 Competenze:", "skippable": False, "allowed_types": ["text"]},
        #{"question": "📎 Puoi allegare il file del TUO CURRICULUM (opzionale):", "label": "📝 Curriculum:", "skippable": True, "allowed_types": ["document"]},
        {"question": "🔗 LINK al tuo Profilo LinkedIn (opzionale):", "label": "🔗 LinkedIn:", "skippable": True, "allowed_types": ["text"]},
        {"question": "📞 Scrivi qui i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False, "allowed_types": ["text"]}
    ]
}