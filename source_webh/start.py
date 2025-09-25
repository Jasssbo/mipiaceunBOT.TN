#!/usr/bin/env python3
"""
Avvio per deployment su Render.com
Gestisce le variabili d'ambiente e avvia il server webhook
"""
import os
import sys

# Su Render, le variabili sono impostate tramite dashboard, non .env
# Ma per compatibilità, proviamo a caricare il .env se esiste
try:
    from dotenv import load_dotenv
    if os.path.exists("bot_infos_webh.env"):
        load_dotenv("bot_infos_webh.env")
        print("✅ Loaded local .env file")
    else:
        print("📝 Using environment variables from Render")
except ImportError:
    print("📝 python-dotenv not available, using system environment")

# Verifica variabili obbligatorie
required_vars = ["API_ID", "API_HASH", "BOT_TOKEN", "REDIS_URL"]
missing = [var for var in required_vars if not os.getenv(var)]

if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)}")
    print("Configure them in Render dashboard or check your .env file")
    sys.exit(1)

print("✅ All environment variables found")
print(f"📡 Redis URL: {os.getenv('REDIS_URL')[:50]}...")
print(f"🤖 Bot Token: {os.getenv('BOT_TOKEN')[:20]}...")

# Determina se usare Gunicorn (produzione) o Flask dev server
is_production = os.getenv("RENDER") is not None

if is_production:
    print("🏭 Produzione: Avvio con Gunicorn")
    # Su Render, usa Gunicorn per produzione
    port = os.getenv("PORT", "5000")
    workers = os.getenv("WEB_CONCURRENCY", "2")
    
    # Avvia Gunicorn
    os.system(f"gunicorn --bind 0.0.0.0:{port} --workers {workers} --timeout 120 --keep-alive 2 --log-level info wsgi:application")
else:
    print("�️ Sviluppo: Avvio con Flask dev server")
    # Sviluppo locale: usa Flask dev server
    from main import main as start_webhook_server
    start_webhook_server()