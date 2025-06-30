import os
import sys
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ------------------------ CONFIGURAZIONE ------------------------

load_dotenv("bot_infos.env")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHAT_ID = os.getenv("CHAT_ID")

if not all([API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, CHAT_ID]):
    missing = [var for var in ["API_ID", "API_HASH", "BOT_TOKEN", "BOT_USERNAME", "CHAT_ID"] if not locals().get(var)]
    logging.critical(f"Mancano le seguenti variabili di configurazione .env: {', '.join(missing)}")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except:
    logging.critical("API_ID deve essere un intero.")
    sys.exit(1)
try:
    CHAT_ID = int(CHAT_ID)
except:
    logging.critical("CHAT_ID deve essere un intero (ad esempio, con il segno - per canali).")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

bot = Client("job_board_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

CATEGORY_QUESTIONS = {
    "job": [
        {"question": "💼 Inserisci il TITOLO LAVORATIVO che cerchi (es. Fonico):", "label": "💼 Titolo lavorativo richiesto:"},
        {"question": "📜 DESCRIVI LA MANSIONE e ciò di cui si dovrà occupare:", "label": "📜 Descrizione mansione:"},
        {"question": "📍 Inserisci il LUOGO in cui è richiesta questa figura:", "label": "📍 Luogo del lavoro:"},
        {"question": "📞 Inserisci i tuoi CONTATTI (Telefono, Email, Telegram):", "label": "📞 Contatti:"}
    ],
    "project": [
        {"question": "💡 Inserisci il TITOLO DEL PROGETTO:", "label": "💡 Titolo del Progetto:"},
        {"question": "📜 DESCRIVI IL TUO PROGETTO e spiega a quali ambiti è riferito:", "label": "📜 Descrizione del Progetto:"},
        {"question": "🔗 Inserisci un LINK (opzionale):", "label": "🔗 Link:"},
        {"question": "📌 Puoi CARICARE UN FILE (opzionale):", "label": "📌 File allegato:"},
        {"question": "📞 Inserisci i CONTATTI (Telefono, Email, Telegram):", "label": "📞 Contatti:"}
    ],
    "event": [
        {"question": "🎫 Inserisci il NOME DELL'EVENTO:", "label": "🎫 Nome evento:"},
        {"question": "📰 Inviami il VOLANTINO/FLYER dell'EVENTO (come immagine o PDF):", "label": "📰 Flyer:"},
        {"question": "📍 Inserisci il LUOGO dell'evento:", "label": "📍 Luogo:"},
        {"question": "⏰ Inserisci la DATA E ORA dell'evento:", "label": "⏰ Data e ora:"},
        {"question": "💰 Inserisci il COSTO del BIGLIETTO (se gratuito, specifica gratuito):", "label": "💰 Costo biglietto:"},
        {"question": "📞 Inserisci i CONTATTI (Telefono, Email, Telegram):", "label": "📞 Contatti:"}
    ],
    "profile": [
        {"question": "👤 Inserisci il tuo NOME E COGNOME:", "label": "👤 Nome e cognome:"},
        {"question": "💼 Inserisci la tua PROFESSIONE:", "label": "💼 Professione:"},
        {"question": "📜 Breve DESCRIZIONE delle tue competenze (max 5 righe):", "label": "📜 Competenze:"},
        {"question": "📎 Puoi ALLEGARE il file del tuo CURRICULUM (word o pdf):", "label": "📌 Curriculum:"},
        {"question": "🔗 Inserisci il LINK al tuo Profilo LinkedIn (opzionale):", "label": "🔗 Profilo LinkedIn:"},
        {"question": "📞 Inserisci i tuoi CONTATTI (Telefono, Email, Telegram):", "label": "📞 Contatti:"}
    ]
}

POINTER_MESSAGE_IDS = {
    "job": 466,
    "project": 467,
    "event": 463,
    "profile": 468
}

user_data = {}

# ------------------------ UTILITY ------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60), retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
async def safe_delete(client: Client, chat_id: int, message_id: int):
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass

async def send_clean_message(client: Client, user_id: int, chat_id: int, text: str, reply_markup=None) -> Message:
    last_msg_id = user_data.get(user_id, {}).get("last_bot_message_id")
    if last_msg_id:
        await safe_delete(client, chat_id, last_msg_id)
    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)
    if user_id not in user_data:
        user_data[user_id] = {"step": 0, "answers": {}, "file": None, "file_type": None, "messages_to_delete": [], "last_bot_message_id": None}
    user_data[user_id]["last_bot_message_id"] = sent.id
    user_data[user_id]["messages_to_delete"].append(sent.id)
    return sent

# ------------------------ /start ------------------------

# MENU PRINCIPALE con bottone "Come eliminare un annuncio"
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data[user_id] = {
        "step": 0,
        "category": None,
        "answers": {},
        "file": None,
        "file_type": None,
        "messages_to_delete": [],
        "last_bot_message_id": None
    }
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Profilo Lavorativo", callback_data="new_profile")],
        [InlineKeyboardButton("ℹ️ Come eliminare un annuncio", callback_data="how_to_delete")]
    ])
    await send_clean_message(client, user_id, chat_id, "👋 Benvenuto! Scegli cosa vuoi pubblicare:", buttons)

# Spiegazione per eliminare un annuncio
@bot.on_callback_query(filters.create(lambda _, __, query: query.data == "how_to_delete"))
async def how_to_delete_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "Per eliminare un tuo annuncio:\n"
        "1️⃣ Copia l'ID che trovi all'inizio dell'annuncio pubblicato nel canale.\n"
        "2️⃣ Invia questo comando in chat privata con il bot:\n\n"
        "`/elimina <ID_annuncio>`\n\n"
        "Esempio: `/elimina 12345`"
    )

# Comando elimina annuncio
@bot.on_message(filters.command("elimina") & filters.private)
async def elimina_annuncio(client, message: Message):
    user = message.from_user
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply(
            "❌ Uso corretto: /elimina <ID_annuncio>\n"
            "Esempio: `/elimina 12345`"
        )
        return

    msg_id = int(parts[1])
    try:
        msg = await client.get_messages(CHAT_ID, msg_id)
        if not msg or not msg.text:
            await message.reply("❌ Annuncio non trovato. Controlla di aver inserito l'ID giusto.")
            return

        author = f"@{user.username}" if user.username else user.first_name

        if author not in msg.text:
            await message.reply("❌ Non puoi eliminare questo annuncio perché non risulti come autore.")
            return

        await client.delete_messages(CHAT_ID, msg_id)
        await message.reply("✅ Annuncio eliminato con successo dal canale.")
    except Exception as e:
        logging.exception("Errore durante eliminazione annuncio")
        await message.reply("❌ Errore durante l'eliminazione dell'annuncio.")

# ------------------------ CALLBACK HANDLER ------------------------

@bot.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    try:
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            user_data[user_id].update({
                "category": cat,
                "step": 0,
                "answers": {},
                "file": None,
                "file_type": None,
                "messages_to_delete": []
            })
            first_question = CATEGORY_QUESTIONS[cat][0]["question"]
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, chat_id, first_question, buttons)

        elif data == "back_to_menu":
            if user_id in user_data:
                for mid in user_data[user_id].get("messages_to_delete", []):
                    await safe_delete(client, chat_id, mid)
                user_data.pop(user_id, None)
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
                [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
                [InlineKeyboardButton("💡 Call per un Progetto", callback_data="new_project")],
                [InlineKeyboardButton("👤 Profilo Lavorativo", callback_data="new_profile")],
                [InlineKeyboardButton("ℹ️ Come eliminare un annuncio", callback_data="how_to_delete")]
            ])
            await send_clean_message(client, user_id, chat_id, "🏠 Menù principale. Scegli un'azione:", buttons)

        elif data == "how_to_delete":
            await callback_query.message.edit_text(
                "Per eliminare un tuo annuncio:\n"
                "1️⃣ Copia l'ID che trovi all'inizio dell'annuncio pubblicato nel canale.\n"
                "2️⃣ Invia questo comando in chat privata con il bot:\n\n"
                "`/elimina <ID_annuncio>`\n\n"
                "Esempio: `/elimina 12345`"
            )

        elif data.startswith("confirm_") or data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            if data.startswith("confirm_"):
                posted_message = await publish_announcement(client, uid)
                if posted_message:
                    await client.send_message(
                        chat_id,
                        f"✅ Il tuo annuncio è stato pubblicato!\n\n"
                        f"🔎 **Come eliminarlo?**\n"
                        f"Se vuoi cancellare il tuo annuncio in futuro, ti basta inviare questo comando:\n\n"
                        f"`/elimina {posted_message.id}`\n\n"
                        f"Trovi l'ID annuncio anche all'inizio del messaggio pubblicato nel canale."
                    )
                    try:
                        prev_id = user_data[uid].get("preview_msg_id")
                        if prev_id:
                            await safe_delete(client, chat_id, prev_id)
                    except Exception:
                        pass
                else:
                    await client.send_message(chat_id, "❌ Errore: annuncio non pubblicato.")
            else:
                await client.send_message(chat_id, "❌ Inserimento annullato. Nessun annuncio è stato pubblicato.")
                try:
                    prev_id = user_data[uid].get("preview_msg_id")
                    if prev_id:
                        await safe_delete(client, chat_id, prev_id)
                except Exception:
                    pass
            for mid in user_data.get(uid, {}).get("messages_to_delete", []):
                await safe_delete(client, chat_id, mid)
            user_data.pop(uid, None)

        elif data == "back_to_question":
            info = user_data.get(user_id)
            if info and info.get("step", 0) > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                for mid in info.get("messages_to_delete", []):
                    await safe_delete(client, chat_id, mid)
                info["messages_to_delete"].clear()
                prev_question = CATEGORY_QUESTIONS[info["category"]][info["step"]]["question"]
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Domanda precedente", callback_data="back_to_question")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await send_clean_message(client, user_id, chat_id, prev_question, buttons)
    except Exception as e:
        logging.exception("Errore nel gestore dei callback")
        await client.send_message(chat_id, f"❌ Errore interno: {str(e)}")
        user_data.pop(user_id, None)

# ------------------------ RACCOLTA DATI ------------------------

@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id not in user_data or user_data[user_id].get("category") is None:
        return
    try:
        await safe_delete(client, chat_id, message.id)
        info = user_data[user_id]
        cat = info["category"]
        step = info.get("step", 0)
        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]
        if message.photo or message.document:
            info["answers"][label_text] = "📎 File allegato."
            info["file"] = message.photo.file_id if message.photo else message.document.file_id
            info["file_type"] = "photo" if message.photo else "document"
        elif message.text:
            if "(opzionale)" in question_text.lower() and message.text.strip().lower() == "/skip":
                info["answers"][label_text] = "Saltato."
            else:
                info["answers"][label_text] = message.text.strip()
        info["step"] += 1
        if info["step"] < len(CATEGORY_QUESTIONS[cat]):
            next_q = CATEGORY_QUESTIONS[cat][info["step"]]["question"]
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Domanda precedente", callback_data="back_to_question")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, chat_id, next_q, buttons)
        else:
            announcement_text = f"📢 **Anteprima del tuo annuncio**\n\n"
            for label, answer in info["answers"].items():
                announcement_text += f"**{label}**\n{answer}\n\n"
            if info.get("file"):
                announcement_text += "📎 *Hai allegato un file a questo annuncio.*\n\n"
            preview_msg = await client.send_message(chat_id, announcement_text)
            info["preview_msg_id"] = preview_msg.id
            confirm_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, chat_id, "✅ Confermi la pubblicazione di questo annuncio?", confirm_buttons)
    except Exception as e:
        logging.exception("Errore nella raccolta dati")
        await client.send_message(chat_id, f"❌ Si è verificato un errore: {str(e)}")
        user_data.pop(user_id, None)

# ------------------------ PUBBLICAZIONE ------------------------
async def publish_announcement(client: Client, user_id: int) -> Message:
    info = user_data.get(user_id)
    if not info:
        return None
    cat = info.get("category")
    user = await client.get_users(user_id)
    author = f"@{user.username}" if user.username else user.first_name
    if cat == "job":
        category_name = "Annuncio di Lavoro"
    elif cat == "project":
        category_name = "Progetto"
    elif cat == "event":
        category_name = "Evento"
    elif cat == "profile":
        category_name = "Profilo"
    else:
        category_name = cat.capitalize() if cat else ""
    text = (
        f"📢 **Nuovo {category_name}**\n"
        f"ID annuncio: {{ID}}\n"
        f"Pubblicato da: {author}\n\n"
    )
    for label, answer in info["answers"].items():
        if label.lower().startswith("📌 file") and info.get("file"):
            continue
        text += f"**{label}**\n{answer}\n\n"
    pointer_id = POINTER_MESSAGE_IDS.get(cat)
    try:
        if info.get("file"):
            if info.get("file_type") == "photo":
                posted_msg = await client.send_photo(CHAT_ID, info["file"], caption=text.replace("{ID}", "in caricamento..."), reply_to_message_id=pointer_id if pointer_id else None)
            else:
                posted_msg = await client.send_document(CHAT_ID, info["file"], caption=text.replace("{ID}", "in caricamento..."), reply_to_message_id=pointer_id if pointer_id else None)
        else:
            posted_msg = await client.send_message(CHAT_ID, text.replace("{ID}", "in caricamento..."), reply_to_message_id=pointer_id if pointer_id else None)
        # Modifica il messaggio per inserire l'ID reale
        new_text = text.replace("{ID}", str(posted_msg.id))
        await posted_msg.edit_text(new_text)
        logging.info(f"Annuncio pubblicato sul canale (ID messaggio: {posted_msg.id})")
        return posted_msg
    except Exception as e:
        logging.exception(f"Errore durante la pubblicazione sul canale: {e}")
        return None

# ------------------------ ELIMINAZIONE ANNUNCIO ------------------------
@bot.on_message(filters.command("elimina") & filters.private)
async def elimina_annuncio(client, message: Message):
    user = message.from_user
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply(
            "❌ Uso corretto: /elimina <ID_annuncio>\n"
            "Esempio: `/elimina 12345`"
        )
        return
    msg_id = int(parts[1])
    try:
        msg = await client.get_messages(CHAT_ID, msg_id)
        if not msg or not msg.text:
            await message.reply("❌ Annuncio non trovato. Controlla di aver inserito l'ID giusto.")
            return
        author = f"@{user.username}" if user.username else user.first_name
        if author not in msg.text:
            await message.reply("❌ Non puoi eliminare questo annuncio perché non risulti come autore.")
            return
        await client.delete_messages(CHAT_ID, msg_id)
        await message.reply("✅ Annuncio eliminato con successo dal canale.")
    except Exception as e:
        logging.exception("Errore durante eliminazione annuncio")
        await message.reply("❌ Errore durante l'eliminazione dell'annuncio.")


# ------------------------ AVVIO ------------------------

if __name__ == "__main__":
    logging.info("🤖 Avvio del bot...")
    bot.run()
    logging.info("🔚 Bot arrestato.")