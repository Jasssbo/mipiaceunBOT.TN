#!/usr/bin/env python3
"""
Entry point per bot webhook su Render.com
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
        print("📝 Variabili caricate da bot_infos_webh.env")
    elif os.path.exists("../bot_infos.env"):
        load_dotenv("../bot_infos.env")
        print("📝 Variabili caricate da ../bot_infos.env")
except ImportError:
    print("⚠️ python-dotenv non disponibile, uso variabili sistema")

def check_required_env():
    """Verifica che le variabili obbligatorie siano definite"""
    required = [
        "API_ID", "API_HASH", "BOT_TOKEN", "CHANNEL_ID", 
        "ADMIN_ID", "REDIS_URL", "WEBHOOK_URL"
    ]
    
    missing = []
    for var in required:
        value = os.environ.get(var)
        if not value:
            missing.append(var)
        else:
            # Maschera valori sensibili nel log
            if var in ["BOT_TOKEN", "API_HASH", "REDIS_URL"]:
                masked = value[:6] + "..." + value[-4:] if len(value) > 10 else "***"
                print(f"✅ {var}: {masked}")
            else:
                print(f"✅ {var}: {value}")
    
    if missing:
        print(f"❌ Variabili mancanti: {', '.join(missing)}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Avvio bot webhook (DEV mode)...")
    
    # Verifica configurazione
    if not check_required_env():
        print("💥 Configurazione incompleta!")
        sys.exit(1)
    
    # Avvia server Flask in dev mode
    print("🌐 Avvio server Flask DEV...")
    from main import main
    main()