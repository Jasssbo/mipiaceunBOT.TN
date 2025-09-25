"""
Main Flask webhook app per bot Telegram (versione webhook).
Sostituisce bot.run() con un web server che riceve updates da Telegram.
"""
import os
import sys
import logging
import asyncio
from threading import Thread, Lock
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from pyrogram import filters

# Importa l'istanza del bot dal modulo di configurazione
from config import bot, storage

# Identità del bot (riempita a runtime)
bot_identity = {"username": None, "id": None}

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

# Handler registration is automatic via decorators when modules are imported above
# No need for explicit imports here

# Crea Flask app
app = Flask(__name__)

# Global event loop per gestire operazioni async
loop = None
loop_thread = None
bot_ready = False
_startup_lock = Lock()
_startup_done = False

# Debug ping handler (specific, non-conflicting)
@bot.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message):
    """Specific ping handler for testing - non-conflicting with other handlers."""
    try:
        uid = getattr(getattr(message, "from_user", None), "id", None)
        username = getattr(getattr(message, "from_user", None), "username", None)
        logging.info(f"[🔥 PING] user={uid} (@{username}) requested ping")
        await message.reply("🏓 pong - bot is alive!")
    except Exception as e:
        logging.exception(f"[PING] error: {e}")

# Opzionale: echo di debug per QUALSIASI DM testuale (abilita con env DEBUG_ECHO=true)
if os.getenv("DEBUG_ECHO", "false").lower() == "true":
    @bot.on_message(filters.private & filters.text & ~filters.command, group=98)
    async def __debug_echo(client, message):
        try:
            await message.reply(f"🔊 Echo di debug: {message.text[:200]}")
        except Exception as e:
            logging.exception(f"[DEBUG ECHO] error: {e}")

async def initialize_bot():
    """Inizializza il bot senza avviare polling."""
    global bot_ready
    try:
        await bot.start()
        me = await bot.get_me()
        # Salva identità bot per debug/health
        try:
            bot_identity["username"] = getattr(me, 'username', None)
            bot_identity["id"] = getattr(me, 'id', None)
        except Exception:
            pass
        bot_ready = True
        logging.info(f"🤖 Bot connesso: @{getattr(me, 'username', None)} (id={getattr(me, 'id', None)})")

        # Note: Pyrogram non ha get_webhook_info (è Bot API)
        # Se hai webhook attivo, rimuovilo manualmente con:
        # curl -X POST 'https://api.telegram.org/bot<TOKEN>/deleteWebhook'
        logging.info("💡 Se il bot non risponde, verifica che non ci sia un webhook attivo")
        logging.info("💡 Comando: curl -X POST 'https://api.telegram.org/bot<TOKEN>/deleteWebhook'")

        # Health check Redis
        if storage.health_check():
            logging.info("✅ Redis connection healthy")
        else:
            logging.warning("⚠️ Redis connection issues")

        # Start keep-alive task on Render (better environment detection + guard flag)
        render_external_url = os.getenv('RENDER_EXTERNAL_URL')
        keep_alive_enabled = os.getenv('KEEP_ALIVE', 'true').lower() == 'true'
        if keep_alive_enabled and (render_external_url or os.getenv('RENDER_SERVICE_ID')):
            # Schedule task in the correct event loop
            current_loop = asyncio.get_event_loop()
            current_loop.create_task(keep_alive_task())
            logging.info("🔄 Keep-alive task started for Render environment")

    except Exception as e:
        logging.error(f"❌ Errore inizializzazione bot: {e}")
        bot_ready = False

async def keep_alive_task():
    """Keep the service alive by making HTTP requests to itself every 4 minutes."""
    render_url = os.getenv('RENDER_EXTERNAL_URL', 'https://mipiaceunbot-tn.onrender.com')
    session = requests.Session()
    
    while True:
        try:
            await asyncio.sleep(240)  # 4 minutes
            resp = session.get(f"{render_url}/", timeout=15)
            if resp.status_code == 200:
                logging.info("🔄 Keep-alive ping successful")
            else:
                logging.warning(f"⚠️ Keep-alive ping failed: {resp.status_code}")
        except Exception as e:
            logging.error(f"❌ Keep-alive ping error: {e}")
        except asyncio.CancelledError:
            logging.info("🛑 Keep-alive task cancelled")
            break

def start_bot_once():
    """Avvia l'event loop e inizializza il bot una sola volta in modo thread-safe."""
    global loop, loop_thread, _startup_done
    if _startup_done:
        return
    with _startup_lock:
        if _startup_done:
            return
        
        def start_loop():
            global loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_forever()

        loop_thread = Thread(target=start_loop, daemon=True)
        loop_thread.start()

        # Attendi che l'event loop sia pronto
        import time
        for _ in range(20):
            if loop is not None:
                break
            time.sleep(0.1)

        if loop is None:
            logging.critical("Impossibile avviare l'event loop")
            return

        try:
            fut = asyncio.run_coroutine_threadsafe(initialize_bot(), loop)
            fut.result(timeout=30)
            _startup_done = True
        except Exception as e:
            logging.error(f"❌ Errore inizializzazione bot: {e}")

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

@app.before_first_request
def __ensure_bot_started():
    """Assicura l'avvio del bot nel contesto del worker di Gunicorn."""
    start_bot_once()

@app.route('/')
def health_check():
    """Health check endpoint per Render."""
    logging.info(f"[HEALTH] Health check called - bot_ready={bot_ready}")
    status = {
        "status": "ok",
        "bot_ready": bot_ready,
        "redis_health": storage.health_check() if storage else False,
        "timestamp": datetime.now().isoformat(),
        "bot_username": bot_identity.get("username"),
        "bot_id": bot_identity.get("id"),
        "message": "Send /ping to bot for test" if bot_ready else "Bot initializing..."
    }
    return jsonify(status)

# Logger non invasivo per DM: non risponde, solo logga, per verificare che arrivino gli update
@bot.on_message(filters.private, group=99)
async def __debug_private_log(client, message):
    try:
        uid = getattr(getattr(message, "from_user", None), "id", None)
        uname = getattr(getattr(message, "from_user", None), "username", None)
        txt = getattr(message, "text", None)
        logging.info(f"[DEBUG DM] incoming: user={uid} (@{uname}) text='{txt}'")
    except Exception as e:
        logging.exception(f"[DEBUG DM] error: {e}")

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

@app.route('/send_test', methods=['POST', 'GET'])
def send_test_message():
    """Invia un DM di prova a uno user_id per verificare che il bot riesca a spedire messaggi.
    Protezione semplice: richiede un segreto in query/body ?secret=...
    Imposta SEND_TEST_SECRET nelle variabili di ambiente su Render e passa lo stesso valore qui.
    Esempio: GET /send_test?secret=...&user_id=123456&text=Ciao
    """
    try:
        secret_required = os.getenv('SEND_TEST_SECRET')
        provided = request.args.get('secret') or request.values.get('secret')
        if secret_required and provided != secret_required:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = request.args.get('user_id') or request.values.get('user_id')
        text = request.args.get('text') or request.values.get('text') or "Test dal bot"
        if not user_id:
            return jsonify({"error": "Param user_id mancante"}), 400
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({"error": "user_id non valido"}), 400

        if not loop or loop.is_closed():
            return jsonify({"error": "Event loop non disponibile"}), 500

        fut = asyncio.run_coroutine_threadsafe(bot.send_message(user_id, text), loop)
        msg = fut.result(timeout=15)
        return jsonify({
            "status": "sent",
            "chat_id": msg.chat.id if msg else None,
            "message_id": msg.id if msg else None
        })
    except Exception as e:
        logging.exception(f"[SEND_TEST] errore invio: {e}")
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
        # In dev, assicura avvio bot subito
        start_bot_once()
        if loop:
            asyncio.run_coroutine_threadsafe(setup_webhook(), loop).result(timeout=10)
    except Exception as e:
        logging.warning(f"⚠️ Setup webhook info fallito: {e}")
    
    # Avvia Flask DEV server solo se non siamo sotto Gunicorn
    if not os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn'):
        port = int(os.environ.get("PORT", 5000))
        host = os.environ.get("HOST", "0.0.0.0")
        # Forza debug off per evitare riavvii del reloader in locale
        debug_mode = False
        logging.info(f"🌐 Avvio Flask DEV server su {host}:{port} (debug={debug_mode})")
        app.run(
            host=host,
            port=port,
            debug=debug_mode,
            threaded=True,
            use_reloader=False
        )
    else:
        logging.info("🏭 Sotto Gunicorn - Flask DEV server non avviato")

if __name__ == "__main__":
    main()