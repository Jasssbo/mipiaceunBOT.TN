
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
from modules.core.start import start_handler
from modules.permissions.user_permissions import is_user_allowed_by_username
from modules.user_announcements_interactions import announcement_handler
from modules.user_announcements_interactions.announcement_handler import collect_data_handler
from modules.core.buttons import buttons_callback_handler
from modules.permissions.topic_permissions import topic_guardian_handler
from modules.reports.report_user import report_user_handler
# ------------------------ AVVIO e ARRESTO BOT ------------------------
# --- Avvio e arresto del bot Telegram ---
if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
