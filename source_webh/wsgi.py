"""
WSGI entry point SEMPLIFICATO per Gunicorn su Render.
"""
import logging
import sys

# Configura logging per produzione
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Importa solo l'app Flask, senza inizializzazione duplicata
# L'inizializzazione avviene in main.py
try:
    from main import app
    application = app
    logging.info("✅ App Flask caricata per Gunicorn")
except Exception as e:
    logging.error(f"❌ Errore caricamento app: {e}")
    raise