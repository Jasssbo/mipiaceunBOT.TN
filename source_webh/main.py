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

# IMPORTANTE: Importa tutti i moduli che registrano handler
# Questo è necessario per far funzionare il bot in modalità webhook
try:
    from modules import start, buttons, topic_guardian
    from modules.user_announcements_interactions import collect_data, announcement_compiler, report_user
    logging.info("✅ Handler modules imported successfully")
except ImportError as e:
    logging.error(f"❌ Error importing handler modules: {e}")
    sys.exit(1)

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
    Su Render, il webhook viene registrato manualmente dopo il deploy.
    Non gestiamo webhook dal codice per evitare problemi di permessi.
    """
    logging.info("📝 IMPORTANTE: Dopo il deploy, registra il webhook manualmente:")
    logging.info(f"curl -X POST 'https://api.telegram.org/bot{os.getenv('BOT_TOKEN', '<BOT_TOKEN>')}/setWebhook' \\")
    logging.info("     -d 'url=https://your-app-name.onrender.com/webhook'")
    logging.info("💡 Sostituisci 'your-app-name' con il nome della tua app su Render")

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
        
        # Processa l'update direttamente con i dati JSON
        # Non è necessario convertire in oggetto Update, Pyrogram lo fa internamente
        if loop and not loop.is_closed():
            # Schedula task nell'event loop con i dati JSON originali
            asyncio.run_coroutine_threadsafe(
                process_webhook_update(update_data), 
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

async def process_webhook_update(update_data):
    """
    Processa un update webhook usando il metodo CORRETTO di Pyrogram.
    
    IMPORTANTE: Pyrogram non ha bot.dispatcher.process_update()!
    Il modo corretto è convertire i dati JSON in oggetti Pyrogram e 
    chiamare gli handler direttamente tramite il meccanismo di dispatch.
    """
    try:
        # Il modo corretto per processare update in Pyrogram webhook:
        # 1. Converti JSON in oggetto Update
        from pyrogram.types import Update
        
        # Crea un oggetto Update dai dati JSON
        update = Update._parse(bot, update_data, {})
        
        # 2. Processa l'update usando il sistema interno di Pyrogram
        # Questo chiamerà automaticamente tutti gli handler registrati (@bot.on_message, @bot.on_callback_query, etc.)
        if hasattr(bot, 'dispatcher') and hasattr(bot.dispatcher, 'updates_queue'):
            # Aggiungi update alla coda del dispatcher
            await bot.dispatcher.updates_queue.put(update)
        else:
            # Fallback: chiama direttamente il metodo di handling
            await bot.handle_update(update)
        
        logging.info("[WEBHOOK] Update processato con successo")
        
    except Exception as e:
        logging.exception(f"[WEBHOOK] Errore processamento update: {e}")
        
        # Log dettagli per debug
        try:
            if "message" in update_data:
                from_user = update_data.get("message", {}).get("from", {})
                user_id = from_user.get("id") if from_user else None
                logging.error(f"[WEBHOOK] Update da user_id: {user_id}")
            elif "callback_query" in update_data:
                from_user = update_data.get("callback_query", {}).get("from", {})
                user_id = from_user.get("id") if from_user else None
                logging.error(f"[WEBHOOK] Callback da user_id: {user_id}")
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
            "timestamp": datetime.now().isoformat(),
            "bot_ready": bot_ready
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reinit', methods=['POST'])
def reinit_bot():
    """Endpoint per re-inizializzare il bot in caso di problemi."""
    try:
        if loop and not loop.is_closed():
            # Schedula re-inizializzazione
            future = asyncio.run_coroutine_threadsafe(initialize_bot(), loop)
            future.result(timeout=30)
            
            return jsonify({
                "status": "success",
                "bot_ready": bot_ready,
                "message": "Bot re-inizializzato"
            })
        else:
            return jsonify({"error": "Event loop non disponibile"}), 500
            
    except Exception as e:
        logging.exception(f"[REINIT] Errore re-inizializzazione: {e}")
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
    
    # Inizializza bot (non bloccare se fallisce)
    try:
        asyncio.run_coroutine_threadsafe(initialize_bot(), loop).result(timeout=30)
    except Exception as e:
        logging.error(f"❌ Errore durante inizializzazione: {e}")
        
    if not bot_ready:
        logging.warning("⚠️ Bot non pronto, ma continuo con server HTTP")
        logging.warning("🔧 Il webhook risponderà con bot_not_ready fino a risoluzione")
    
    # Setup webhook se URL fornito
    try:
        asyncio.run_coroutine_threadsafe(setup_webhook(), loop).result(timeout=10)
    except Exception as e:
        logging.warning(f"⚠️ Setup webhook fallito: {e}")
    
    # Avvia Flask server
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logging.info(f"🌐 Server in ascolto su {host}:{port}")
    
    # Determina se siamo in produzione o sviluppo
    is_production = os.environ.get("RENDER") is not None or os.environ.get("RAILWAY") is not None
    
    if is_production:
        # PRODUZIONE: Usa Gunicorn tramite start command su Render
        logging.info("🏭 Modalità produzione - server avviato tramite Gunicorn")
        # Non chiamare app.run() in produzione, Gunicorn gestisce tutto
        logging.info("✅ Applicazione pronta per Gunicorn")
    else:
        # SVILUPPO: Usa Flask dev server
        debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
        logging.info("🛠️ Modalità sviluppo - usando Flask dev server")
        
        app.run(
            host=host,
            port=port,
            debug=debug_mode,
            threaded=True
        )

if __name__ == "__main__":
    main()