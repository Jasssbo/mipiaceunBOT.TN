import logging
from pyrogram import filters
from pyrogram.types import Message

from config import CHAT_ID


def register(app):
    @app.on_message(filters.command("elimina") & filters.private)
    async def elimina_annuncio_handler(client, message: Message):
        user = message.from_user
        parts = message.text.strip().split()

        if len(parts) != 2 or not parts[1].isdigit():
            await message.reply("❌ Uso corretto: /elimina <ID_annuncio>")
            return

        msg_id = int(parts[1])

        try:
            msg = await client.get_messages(CHAT_ID, msg_id)
            if not msg or (not msg.text and not msg.caption):
                await message.reply("❌ Impossibile trovare l'annuncio con questo ID.")
                return

            author = f"@{user.username}" if user.username else user.first_name
            body = msg.text or msg.caption or ""
            if author not in body:
                await message.reply("❌ Non sei l'autore di questo annuncio e non puoi eliminarlo.")
                return

            await client.delete_messages(CHAT_ID, msg_id)
            await message.reply(f"✅ Annuncio eliminato con successo.\nID annuncio: {msg_id}")
        except Exception:
            logging.exception("Errore /elimina")
            await message.reply("❌ Errore durante l'eliminazione dell'annuncio.")
