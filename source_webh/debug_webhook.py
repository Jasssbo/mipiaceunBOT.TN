#!/usr/bin/env python3
"""
Test script per verificare lo stato del webhook e testare la connessione del bot.
"""
import os
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client

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
        import aiohttp
        async with aiohttp.ClientSession() as session:
            webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
            async with session.get(webhook_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('ok'):
                        result = data.get('result', {})
                        webhook_url = result.get('url', '')
                        pending_updates = result.get('pending_update_count', 0)
                        
                        print(f"📡 Webhook URL: {webhook_url or 'NESSUNO (✅ CORRETTO)'}")
                        print(f"📊 Updates in coda: {pending_updates}")
                        
                        if webhook_url:
                            print("\n⚠️  PROBLEMA TROVATO!")
                            print("Il webhook è ancora attivo. Questo impedisce a Pyrogram di ricevere i messaggi.")
                            print("\n🔧 SOLUZIONE - Rimozione automatica...")
                            
                            # Prova a rimuovere automaticamente
                            delete_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
                            async with session.post(delete_url) as del_response:
                                if del_response.status == 200:
                                    del_data = await del_response.json()
                                    if del_data.get('ok'):
                                        print("✅ Webhook rimosso automaticamente!")
                                    else:
                                        print(f"❌ Rimozione webhook fallita: {del_data}")
                                else:
                                    print(f"❌ Errore HTTP rimozione webhook: {del_response.status}")
                        else:
                            print("✅ Configurazione webhook corretta per Pyrogram")
                    else:
                        print(f"❌ Errore API: {data}")
                else:
                    print(f"❌ Errore HTTP: {response.status}")
        
    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(check_webhook_status())