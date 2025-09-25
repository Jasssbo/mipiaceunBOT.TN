"""
Main Flask webhook app per bot Telegram (versione webhook).
Sostituisce bot.run() con un web server che riceve updates da Telegram.
"""
import os
import sys
import logging
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify

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

# Catch‑all debug handler per verificare che il dispatcher riceva gli update
@bot.on_message()
async def __debug_any_message(client, message):
    try:
        uid = getattr(getattr(message, "from_user", None), "id", None)
        txt = getattr(message, "text", None)
        cid = getattr(getattr(message, "chat", None), "id", None)
        logging.info(f"[DEBUG HANDLER] on_message fired: user={uid} chat={cid} text={txt}")
        # Comando di test non invasivo
        if txt and txt.strip().lower() == "/ping":
            await message.reply("pong")
    except Exception as e:
        logging.exception(f"[DEBUG HANDLER] error: {e}")

async def initialize_bot():
    """Inizializza il bot senza avviare polling."""
    global bot_ready
    try:
        await bot.start()
        me = await bot.get_me()
        bot_ready = True
        logging.info(f"🤖 Bot connesso: @{getattr(me, 'username', None)} (id={getattr(me, 'id', None)})")

        # Health check Redis
        if storage.health_check():
            logging.info("✅ Redis connection healthy")
        else:
            logging.warning("⚠️ Redis connection issues")

    except Exception as e:
        logging.error(f"❌ Errore inizializzazione bot: {e}")
        bot_ready = False

# Inizializza subito l'event loop e il bot quando il modulo viene importato
# Questo funziona sia con Gunicorn che con Flask dev server
def init_on_import():
    """Inizializza bot quando il modulo viene importato."""
    global loop, bot_ready
    
    if loop is None:  # Evita inizializzazione multipla
        import asyncio
        from threading import Thread
        
        # Avvia event loop in thread separato
        def start_loop():
            global loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_forever()
            
        loop_thread = Thread(target=start_loop, daemon=True)
        loop_thread.start()
        
        # Aspetta che l'event loop sia pronto
        import time
        time.sleep(1)
        
        # Inizializza bot
        if loop:
            try:
                future = asyncio.run_coroutine_threadsafe(initialize_bot(), loop)
                future.result(timeout=30)
            except Exception as e:
                logging.error(f"❌ Errore inizializzazione bot: {e}")

# Chiama inizializzazione
init_on_import()

def setup_event_loop():
    """Deprecated: l'event loop viene creato in init_on_import()."""
    pass

# initialize_bot spostata prima di init_on_import

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
    Endpoint chiamato da Telegram quando è configurato un Bot API webhook.
    In questa architettura Pyrogram riceve gli update tramite la sua connessione, non dal webhook.
    Quindi qui ignoriamo il payload e rispondiamo 200 per evitare retry.
    Suggerimento: rimuovi il webhook con getWebhookInfo -> url vuoto.
    """
    try:
        # Log minimale per debug e indicazione operativa
        payload = request.get_json(silent=True) or {}
        keys = list(payload.keys())
        logging.info(f"[WEBHOOK] Chiamata ricevuta e ignorata. keys={keys}")
        return jsonify({
            "status": "ignored",
            "hint": "Questo bot usa Pyrogram (no Bot API webhook). Esegui deleteWebhook e assicurati che getWebhookInfo sia vuoto.",
        }), 200
    except Exception as e:
        logging.exception(f"[WEBHOOK] Errore inatteso: {e}")
        return jsonify({"status": "ignored", "error": str(e)}), 200

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
    logging.info("🚀 Avvio webhook server (DEV mode)...")
    # Il bot e l'event loop sono già inizializzati da init_on_import()
    # Setup webhook info (solo log informativo)
    try:
        if loop:
            asyncio.run_coroutine_threadsafe(setup_webhook(), loop).result(timeout=10)
    except Exception as e:
        logging.warning(f"⚠️ Setup webhook info fallito: {e}")
    
    # Avvia Flask DEV server solo se non siamo sotto Gunicorn
    if not os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn'):
        port = int(os.environ.get("PORT", 5000))
        host = os.environ.get("HOST", "0.0.0.0")
        debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
        
        logging.info(f"🌐 Avvio Flask DEV server su {host}:{port} (debug={debug_mode})")
        
        app.run(
            host=host,
            port=port,
            debug=debug_mode,
            threaded=True
        )
    else:
        logging.info("🏭 Sotto Gunicorn - Flask DEV server non avviato")

if __name__ == "__main__":
    main()