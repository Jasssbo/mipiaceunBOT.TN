"""
WSGI entry point per Gunicorn su Render.
Questo file inizializza l'applicazione per la produzione.
"""
import os
import sys
import logging
import asyncio
from threading import Thread

# Configura logging per produzione
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Setup event loop prima di importare main
def setup_event_loop():
    """Setup event loop per operazioni async."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Avvia event loop in thread separato
loop_thread = Thread(target=setup_event_loop, daemon=True)
loop_thread.start()

# Aspetta che l'event loop sia pronto
import time
time.sleep(1)

# Importa e inizializza app
from main import app, initialize_bot, loop

# Inizializza bot all'avvio
if loop:
    try:
        future = asyncio.run_coroutine_threadsafe(initialize_bot(), loop)
        future.result(timeout=30)
        logging.info("✅ Bot inizializzato per produzione")
    except Exception as e:
        logging.error(f"❌ Errore inizializzazione bot in produzione: {e}")

# Esporta app per Gunicorn
application = app

if __name__ == "__main__":
    # Fallback per esecuzione diretta
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)