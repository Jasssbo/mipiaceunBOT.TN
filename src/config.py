import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv("bot_infos.env")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID") or 0)

missing = [k for k, v in {
    "API_ID": API_ID, "API_HASH": API_HASH, "BOT_TOKEN": BOT_TOKEN, "CHAT_ID": CHAT_ID}.items() if not v]

if missing:
    logging.critical(f"Missing required .env variables: {', '.join(missing)}")
    sys.exit(1)
