import sys
import logging
from pyrogram import Client

from config import API_ID, API_HASH, BOT_TOKEN
from handlers import register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Client("job_board_bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

register_handlers(app)

if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    app.run()
    logging.info("🔚 Arresto bot...")
