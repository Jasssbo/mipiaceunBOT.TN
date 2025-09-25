"""
Main Flask webhook app per bot Telegram (versione webhook).
Sostituisce bot.run() con un web server che riceve updates da Telegram.
"""
import os
import sys
import logging
import json
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify
from pyrogram.types import Update
from threading import Thread

# Importa l'istanza del bot dal modulo di configurazione
from config import bot, storage

# Configurazione del formato e del livello del testo dei log, per il debug e il monitoraggio.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Importa gli handler per attivarli (necessario per registrazione)
from modules.start import start_handler
from modules.user_announcements_interactions import announcement_compiler
from modules.user_announcements_interactions.collect_data import collect_data_handler
from modules.buttons import buttons_callback_handler
from modules.topic_guardian import topic_guardian_handler
from modules.user_announcements_interactions.report_user import report_user_handler, annulla_report_handler

# Crea Flask app
app = Flask(__name__)

# Global event loop per gestire operazioni async
loop = None
bot_ready = False

def setup_event_loop():
    """Setup event loop per operazioni async in thread separato."""
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_forever()

async def initialize_bot():
    """Inizializza il bot senza avviare polling."""
    global bot_ready
    try:
        await bot.start()
        bot_ready = True
        logging.info("🤖 Bot inizializzato con successo per webhook")
        
        # Health check Redis
        if storage.health_check():
            logging.info("✅ Redis connection healthy")
        else:
            logging.warning("⚠️ Redis connection issues")
            
    except Exception as e:
        logging.error(f"❌ Errore inizializzazione bot: {e}")
        bot_ready = False

async def setup_webhook():
    """
    Su Render, il webhook deve essere registrato manualmente dopo il deploy.
    Questo serve solo per pulire eventuali webhook esistenti.
    """
    try:
        # Rimuovi webhook esistente per evitare conflitti
        await bot.delete_webhook()
        logging.info("🗑️ Webhook esistenti rimossi")
        
        # Log dell'URL che dovrà essere registrato manualmente
        logging.info("📝 IMPORTANTE: Registra manualmente il webhook con:")
        logging.info("curl -X POST 'https://api.telegram.org/bot<BOT_TOKEN>/setWebhook' -d 'url=https://your-app.onrender.com/webhook'")
            
    except Exception as e:
        logging.error(f"❌ Errore setup webhook: {e}")

@app.route('/')
def health_check():
    """Health check endpoint per Render."""
    status = {
        "status": "ok",
        "bot_ready": bot_ready,
        "redis_health": storage.health_check() if storage else False,
        "timestamp": datetime.now().isoformat()
    }
    return jsonify(status)

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Endpoint principale webhook che riceve updates da Telegram.
    Deve sempre ritornare HTTP 200 per evitare retry di Telegram.
    """
    try:
        # Verifica che il bot sia pronto
        if not bot_ready:
            logging.warning("[WEBHOOK] Bot non ancora pronto, ignoro update")
            return jsonify({"status": "bot_not_ready"}), 200
        
        # Ottieni dati JSON dalla richiesta
        update_data = request.get_json()
        if not update_data:
            logging.warning("[WEBHOOK] Nessun dato JSON ricevuto")
            return jsonify({"status": "no_data"}), 200
        
        # Log dell'update ricevuto (senza dati sensibili)
        update_type = "unknown"
        if "message" in update_data:
            update_type = "message"
        elif "callback_query" in update_data:
            update_type = "callback_query"
        elif "edited_message" in update_data:
            update_type = "edited_message"
            
        logging.info(f"[WEBHOOK] Ricevuto update tipo: {update_type}")
        
        # Converti in oggetto Update di Pyrogram
        try:
            update = Update._parse(bot, update_data, {})
        except Exception as e:
            logging.error(f"[WEBHOOK] Errore parsing update: {e}")
            return jsonify({"status": "parse_error"}), 200
        
        # Processa l'update in modo asincrono
        if loop and not loop.is_closed():
            # Schedula task nell'event loop
            asyncio.run_coroutine_threadsafe(
                process_update_async(update), 
                loop
            )
        else:
            logging.error("[WEBHOOK] Event loop non disponibile")
            return jsonify({"status": "loop_error"}), 200
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        # Log errore ma ritorna sempre 200
        logging.exception(f"[WEBHOOK] Errore critico: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

async def process_update_async(update):
    """
    Processa un update in modo asincrono.
    Gestisce tutti gli errori per evitare crash del webhook.
    """
    try:
        # Invia update ai handler del bot
        await bot.handle_update(update)
        
    except Exception as e:
        logging.exception(f"[UPDATE] Errore processamento update: {e}")
        
        # In caso di errore, log dettagli per debug
        try:
            if hasattr(update, 'message') and update.message:
                user_id = update.message.from_user.id if update.message.from_user else None
                logging.error(f"[UPDATE] Errore con messaggio da user_id: {user_id}")
            elif hasattr(update, 'callback_query') and update.callback_query:
                user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
                logging.error(f"[UPDATE] Errore con callback da user_id: {user_id}")
        except:
            pass

@app.route('/stats')
def stats():
    """Endpoint per statistiche Redis (per debug)."""
    try:
        if not storage:
            return jsonify({"error": "Storage non disponibile"}), 500
            
        stats = {
            "redis_health": storage.health_check(),
            "active_keys": storage.cleanup_expired(),
            "all_sessions": len(storage.get_all_user_sessions()),
            "timestamp": datetime.now().isoformat()
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handler per 404."""
    return jsonify({"error": "Endpoint non trovato"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handler per errori interni."""
    logging.error(f"[APP] Errore interno: {error}")
    return jsonify({"error": "Errore interno del server"}), 500

def main():
    """Funzione principale per avvio webhook server."""
    global loop
    
    logging.info("🚀 Avvio webhook server...")
    
    # Setup event loop in thread separato
    loop_thread = Thread(target=setup_event_loop, daemon=True)
    loop_thread.start()
    
    # Aspetta che l'event loop sia pronto
    import time
    time.sleep(1)
    
    # Inizializza bot
    asyncio.run_coroutine_threadsafe(initialize_bot(), loop).result(timeout=30)
    
    if not bot_ready:
        logging.error("❌ Bot non pronto, uscita")
        sys.exit(1)
    
    # Setup webhook se URL fornito
    try:
        asyncio.run_coroutine_threadsafe(setup_webhook(), loop).result(timeout=10)
    except Exception as e:
        logging.warning(f"⚠️ Setup webhook fallito: {e}")
    
    # Avvia Flask server
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logging.info(f"🌐 Server in ascolto su {host}:{port}")
    
    # In produzione usa un WSGI server, per dev va bene Flask built-in
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        threaded=True
    )

if __name__ == "__main__":
    main()