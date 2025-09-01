
"""
Punto di avvio del bot.
Esegui questo file per avviare il bot.
"""
import logging
import sys

# Importa l'istanza del bot dal modulo di configurazione
from config import bot


# Configurazione del formato e del livello del testo dei log, per il debug e il monitoraggio.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
# Importa gli handler per attivarli
from modules.start import start_handler
from modules.user_announcements_interactions import announcement_compiler
from modules.user_announcements_interactions.collect_data import collect_data_handler
from modules.buttons import buttons_callback_handler
from modules.topic_guardian import topic_guardian_handler
from modules.user_announcements_interactions.report_user import report_user_handler, annulla_report_handler
# ------------------------ AVVIO e ARRESTO BOT ------------------------
# --- Avvio e arresto del bot Telegram ---
if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
