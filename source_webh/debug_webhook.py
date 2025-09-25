#!/usr/bin/env python3
"""
Test script per verificare lo stato del webhook e testare la connessione del bot.
"""
import os
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client
import requests

# Carica variabili ambiente
load_dotenv("bot_infos_webh.env")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def check_webhook_status():
    """Verifica lo stato del webhook di Telegram."""
    
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        print("❌ Variabili ambiente mancanti!")
        return
    
    bot = Client(
        name=":memory:",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True
    )
    
    try:
        await bot.start()
        print("✅ Bot connesso")
        
        me = await bot.get_me()
        print(f"🤖 Bot: @{me.username} (ID: {me.id})")
        
        # Controlla webhook usando HTTP API (Pyrogram non ha get_webhook_info)
        webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        resp = requests.get(webhook_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('ok'):
                result = data.get('result', {})
                url = result.get('url', '')
                pending_updates = result.get('pending_update_count', 0)

                print(f"📡 Webhook URL: {url or 'NESSUNO (✅ CORRETTO)'}")
                print(f"📊 Updates in coda: {pending_updates}")

                if url:
                    print("\n⚠️  PROBLEMA TROVATO!")
                    print("Il webhook è ancora attivo. Questo impedisce a Pyrogram di ricevere i messaggi.")
                    print("\n🔧 SOLUZIONE - Rimozione automatica...")

                    delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
                    del_resp = requests.post(delete_url, timeout=15)
                    if del_resp.status_code == 200:
                        del_data = del_resp.json()
                        if del_data.get('ok'):
                            print("✅ Webhook rimosso automaticamente!")
                        else:
                            print(f"❌ Rimozione webhook fallita: {del_data}")
                    else:
                        print(f"❌ Errore HTTP rimozione webhook: {del_resp.status_code}")
                else:
                    print("✅ Configurazione webhook corretta per Pyrogram")
            else:
                print(f"❌ Errore API: {data}")
        else:
            print(f"❌ Errore HTTP: {resp.status_code}")
        
    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(check_webhook_status())