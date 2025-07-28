"""
Punto di avvio del bot.
Esegui questo file per avviare il bot.
"""
import logging
import sys
from pyrogram import Client
from source.config import API_ID, API_HASH, BOT_TOKEN

# Istanza del client Pyrogram
bot = Client("job_board_bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

# Configurazione del formato e del livello del testo dei log, per il debug e il monitoraggio.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
# Importa gli handler per attivarli
from source.modules.user_announcements_interactions.start import start_handler
from source.modules.user_announcements_interactions import announcement_compiler
from source.modules.user_announcements_interactions.collect_data import collect_data_handler
from source.modules.user_announcements_interactions.buttons import buttons_callback_handler
from source.modules.topic_guardian import topic_guardian_handler

# Richiama le funzioni per avviarle
# start_handler: Avvia il bot e gestisce il comando /start.
start_handler()
# announcement_compiler: Gestisce la compilazione degli annunci.
announcement_compiler()
# collect_data_handler: Gestisce la raccolta dei dati dagli utenti.
collect_data_handler()
# buttons_callback_handler: Gestisce i callback dei pulsanti.
buttons_callback_handler()
# topic_guardian_handler: Gestisce la protezione dei topic e le autorizzazioni degli utenti.
topic_guardian_handler()

# ------------------------ AVVIO e ARRESTO BOT ------------------------
# --- Avvio e arresto del bot Telegram ---
if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
