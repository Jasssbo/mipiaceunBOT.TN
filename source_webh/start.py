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

# Avvia l'applicazione Flask con inizializzazione bot
from main import main as start_webhook_server

if __name__ == "__main__":
    # Su Render, usa la porta fornita dal sistema
    os.environ.setdefault("PORT", "5000")
    
    print("🚀 Starting webhook server on Render...")
    start_webhook_server()