#!/usr/bin/env python3
"""
Keep-alive script per mantenere attivo il servizio Render.
Invia una richiesta HTTP ogni 5 minuti al tuo servizio.
"""
import requests
import time
import logging
from datetime import datetime

# URL del tuo servizio su Render
SERVICE_URL = "https://mipiaceunbot-tn.onrender.com"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ping_service():
    """Invia una richiesta GET al servizio."""
    try:
        response = requests.get(f"{SERVICE_URL}/", timeout=30)
        status = "✅" if response.status_code == 200 else "⚠️"
        logger.info(f"{status} Ping {datetime.now()}: {response.status_code}")
        
        # Log dettagli risposta
        if response.status_code == 200:
            try:
                data = response.json()
                bot_ready = data.get('bot_ready', False)
                logger.info(f"   Bot ready: {bot_ready}")
            except:
                pass
        
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Errore ping {datetime.now()}: {e}")
        return False

def keep_alive():
    """Loop principale per mantenere il servizio attivo."""
    logger.info(f"🚀 Avvio keep-alive per {SERVICE_URL}")
    logger.info("⏰ Ping ogni 5 minuti...")
    
    while True:
        ping_service()
        # Attendi 5 minuti (300 secondi)
        time.sleep(300)

if __name__ == "__main__":
    try:
        keep_alive()
    except KeyboardInterrupt:
        logger.info("🛑 Keep-alive interrotto dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}")