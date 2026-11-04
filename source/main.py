
"""
Punto di avvio del bot.
Esegui questo file per avviare il bot.
"""
import logging
import sys
import os
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# Importa l'istanza del bot dal modulo di configurazione
from config import bot


# Configurazione del formato e del livello del testo dei log, per il debug e il monitoraggio.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Mini server HTTP per soddisfare il port binding di Render sui Web Service gratuiti."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def log_message(self, format, *args):
        # Silenzia i log continui dei ping di Render per non intasare la console
        pass


def _keep_alive_loop(external_url: str) -> None:
    """
    Invia un ping HTTPS leggero ogni 8 minuti verso l'URL pubblico di Render
    per azzerare l'idle timer di 15 minuti senza consumare Redis o DB.
    Include un retry rapido (15s) in caso di glitch di rete transitorio.
    """
    stop_event = threading.Event()
    target_url = f"{external_url.rstrip('/')}/health"
    while not stop_event.wait(480):  # 8 minuti (garantisce almeno 2 tentativi entro la finestra di 15m)
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    target_url,
                    headers={"User-Agent": "mipiaceunBOT-KeepAlive/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                break
            except Exception as e:
                if attempt == 0:
                    stop_event.wait(15)
                else:
                    logging.warning(f"[KEEP-ALIVE] Ping verso {target_url} non riuscito: {e}")


def start_healthcheck_server():
    port_str = os.getenv("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logging.info(f"🌐 Server di health-check Render attivo sulla porta {port}")

        external_url = (
            os.getenv("RENDER_EXTERNAL_URL")
            or os.getenv("KEEP_ALIVE_URL")
            or "https://mipiaceunbot-tn-v1ac.onrender.com"
        ).strip()
        if external_url.startswith(("http://", "https://")):
            ka_thread = threading.Thread(target=_keep_alive_loop, args=(external_url,), daemon=True)
            ka_thread.start()
            logging.info(f"🔄 Keep-alive anti-sleep attivo verso {external_url} (ogni 8m)")
    except Exception as e:
        logging.error(f"Errore durante l'avvio del server di health-check: {e}")


# Importa gli handler per attivarli
from database.repository import init_db
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
    start_healthcheck_server()
    bot.loop.run_until_complete(init_db())
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
