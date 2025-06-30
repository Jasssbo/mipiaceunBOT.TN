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
CHAT_ID = int(os.getenv("CHAT_ID"))

if not all([API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, CHAT_ID]):
    missing = [var for var in ["API_ID", "API_HASH", "BOT_TOKEN", "BOT_USERNAME", "CHAT_ID"] if not locals()[var]]
    logging.critical(f"Missing required .env variables: {', '.join(missing)}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

bot = Client("job_board_bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

CATEGORY_QUESTIONS = {
    "job": [
        {"question": "💼 Inserisci il TITOLO LAVORATIVO che cerchi (es. Fonico):", "label": "💼 Titolo lavorativo richiesto:"},
        {"question": "📜 DESCRIVI LA MANSIONE e ciò di cui si dovrà occupare:", "label": "📜 Descrizione mansione:"},
        {"question": "📍 Inserisci il LUOGO in cui richiedi questa figura:", "label": "📍 Luogo del Lavoro:"},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:"}
    ],
    "project": [
        {"question": "💡 Inserisci il TITOLO DEL PROGETTO:", "label": "💡 Titolo del Progetto:"},
        {"question": "📜 DESCRIVI IL TUO PROGETTO e spiega a quali ambiti è riferito:", "label": "📜 Descrizione del Progetto:"},
        {"question": "📌 Puoi CARICARE UN FILE (opzionale):", "label": "📌 File allegato:"},
        {"question": "🔗 Inserisci un LINK (opzionale):", "label": "🔗 Link:"},
        {"question": "📞 CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:"}
    ],
    "event": [
        {"question": "🎫 Inserisci il NOME DELL'EVENTO:", "label": "🎫 Nome evento:"},
        {"question": "📰 Inserisci il VOLANTINO / FLYER dell'EVENTO:", "label": "📰 Flyer:"},
        {"question": "📍 Inserisci il LUOGO:", "label": "📍 Luogo:"},
        {"question": "⏰ Inserisci la DATA E ORA:", "label": "⏰ Data e ora:"},
        {"question": "💰 Inserisci il COSTO del BIGLIETTO:", "label": "💰 Costo biglietto:"},
        {"question": "📞 Inserisci i CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:"}
    ],
    "profile": [
        {"question": "👤 Inserisci il tuo NOME E COGNOME:", "label": "👤 Nome e cognome:"},
        {"question": "💼 Inserisci la tua PROFESSIONE:", "label": "💼 Professione:"},
        {"question": "📜 Breve descrizione delle competenze (max. 5 righe):", "label": "📜 Competenze:"},
        {"question": "📎 Puoi allegare il file del TUO CURRICULUM (word o pdf):", "label": "📝 Curriculum:"},
        {"question": "🔗 LINK al tuo Profilo LinkedIn:", "label": "🔗 Profilo LinkedIn:"},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:"}
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

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60),
       retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
async def safe_delete(client, chat_id, message_id):
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass

async def send_clean_message(client, user_id, chat_id, text, reply_markup=None):
    last_msg_id = user_data.get(user_id, {}).get("last_bot_message_id")
    if last_msg_id:
        await safe_delete(client, chat_id, last_msg_id)

    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)

    if user_id not in user_data:
        user_data[user_id] = {"last_bot_message_id": None, "messages_to_delete": []}

    user_data[user_id]["last_bot_message_id"] = sent.id
    user_data[user_id]["messages_to_delete"].append(sent.id)

# ------------------------ /start ------------------------

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "step": 0,
        "answers": {},
        "messages_to_delete": [],
        "last_bot_message_id": None
    }

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
    ])

    await send_clean_message(client, user_id, message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)

# ------------------------ CALLBACK HANDLER ------------------------

@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    try:
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            user_data[user_id].update({"category": cat, "step": 0, "answers": {}, "messages_to_delete": []})

            await send_clean_message(
                client,
                user_id,
                chat_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
            )

        elif data == "back_to_menu":
            if user_id in user_data:
                for mid in user_data[user_id].get("messages_to_delete", []):
                    await safe_delete(client, chat_id, mid)
                user_data.pop(user_id, None)

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
                [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
                [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
                [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
            ])
            await send_clean_message(client, user_id, chat_id, "🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?", buttons)

        elif data.startswith("confirm_") or data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            if data.startswith("confirm_"):
                await publish_announcement(client, uid)
                text = "✅ Pubblicato!"
            else:
                text = "❌ Inserimento annullato."

            for mid in user_data.get(uid, {}).get("messages_to_delete", []):
                await safe_delete(client, chat_id, mid)
            user_data[uid]["messages_to_delete"].clear()
            await send_clean_message(client, user_id, chat_id, text)
            user_data.pop(uid, None)

        elif data == "back_to_question":
            info = user_data[user_id]
            if info["step"] > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                for mid in info["messages_to_delete"]:
                    await safe_delete(client, chat_id, mid)
                info["messages_to_delete"].clear()

                q = CATEGORY_QUESTIONS[info["category"]][info["step"]]["question"]
                await send_clean_message(
                    client,
                    user_id,
                    chat_id,
                    q,
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")],
                        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                    ])
                )

    except Exception as e:
        logging.exception("Errore nel callback handler")
        await send_clean_message(client, user_id, chat_id, f"❌ Errore: {str(e)}")

# ------------------------ RACCOLTA DATI ------------------------

@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        return

    try:
        await safe_delete(client, message.chat.id, message.id)

        info = user_data[user_id]
        cat = info["category"]
        step = info["step"]
        question_data = CATEGORY_QUESTIONS[cat][step]
        question_text = question_data["question"]
        label_text = question_data["label"]

        if message.photo or message.document:
            info["answers"][label_text] = "📎 File allegato."
            info["file"] = message.photo.file_id if message.photo else message.document.file_id
            info["file_type"] = "photo" if message.photo else "document"
        elif message.text:
            if "(opzionale)" in question_text.lower() and message.text.lower().strip() == "/skip":
                info["answers"][label_text] = "Saltato."
            else:
                info["answers"][label_text] = message.text.strip()

        info["step"] += 1
        if info["step"] < len(CATEGORY_QUESTIONS[cat]):
            next_q = CATEGORY_QUESTIONS[cat][info["step"]]["question"]
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, message.chat.id, next_q, buttons)
        else:
            announcement_text = f"📢 **Anteprima del tuo {cat.capitalize()}**\n\n"
            for label, a in info["answers"].items():
                announcement_text += f"**{label}**\n{a}\n\n"

            # Invia l'anteprima includendo l'immagine allegata, se presente
            file_id = info.get("file")
            if file_id:
                if info.get("file_type") == "photo":
                    preview_message = await client.send_photo(message.chat.id, file_id, caption=announcement_text)
                else:
                    preview_message = await client.send_document(message.chat.id, file_id, caption=announcement_text)
            else:
                preview_message = await client.send_message(message.chat.id, announcement_text)

            confirm_btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, message.chat.id, "✅ Confermi di voler pubblicare questo annuncio?", confirm_btns)

    except Exception as e:
        logging.exception("Errore nella raccolta dati")

# ------------------------ PUBBLICAZIONE ------------------------

async def publish_announcement(client, user_id):
    info = user_data.get(user_id)
    if not info:
        return

    cat = info["category"]
    text = f"📢 **Nuovo {cat.capitalize()}**\n\n"
    for label, a in info["answers"].items():
        text += f"**{label}**\n{a}\n\n"

    pointer_id = POINTER_MESSAGE_IDS.get(cat)
    file_id = info.get("file")

    if pointer_id:
        try:
            if file_id:
                if info.get("file_type") == "photo":
                    await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
                else:
                    await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
            else:
                await client.send_message(CHAT_ID, text, reply_to_message_id=pointer_id)
        except Exception as e:
            logging.exception(f"Errore durante la pubblicazione: {e}")

# ------------------------ AVVIO ------------------------

if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
