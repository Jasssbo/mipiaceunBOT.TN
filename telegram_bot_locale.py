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
        {"question": "💼 Inserisci il TITOLO LAVORATIVO che cerchi (es. Fonico):", "label": "💼 Titolo lavorativo richiesto:", "skippable": False},
        {"question": "📜 DESCRIVI LA MANSIONE e ciò di cui si dovrà occupare:", "label": "📜 Descrizione mansione:", "skippable": False},
        {"question": "📍 Inserisci il LUOGO in cui richiedi questa figura:", "label": "📍 Luogo del Lavoro:", "skippable": False},
        {"question": "💰 Inserisci il COMPENSO:", "label": "💰 Compenso:", "skippable": True},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False}
    ],
    "project": [
        {"question": "💡 Inserisci il TITOLO DEL PROGETTO:", "label": "💡 Titolo del Progetto:", "skippable": False},
        {"question": "📜 DESCRIVI IL TUO PROGETTO e spiega a quali ambiti è riferito:", "label": "📜 Descrizione del Progetto:", "skippable": False},
        {"question": "🔗 Inserisci un LINK (opzionale):", "label": "🔗 Link:", "skippable": True},
        {"question": "📌 Puoi CARICARE UN FILE (opzionale):", "label": "📌 File allegato:", "skippable": True},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False}
    ],
    "event": [
        {"question": "🎫 Inserisci il NOME DELL'EVENTO:", "label": "🎫 Nome evento:", "skippable": False},
        {"question": "📰 Inserisci il VOLANTINO / FLYER dell'EVENTO:", "label": "📰 Flyer:","skippable": True},
        {"question": "📍 Inserisci il LUOGO:", "label": "📍 Luogo:", "skippable": False},
        {"question": "⏰ Inserisci la DATA E ORA:", "label": "⏰ Data e ora:", "skippable": False},
        {"question": "💰 Inserisci il COSTO del BIGLIETTO:", "label": "💰 Costo biglietto:", "skippable": True},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False}
    ],
    "profile": [
        {"question": "👤 Inserisci il tuo NOME E COGNOME:", "label": "👤 Nome e cognome:", "skippable": False},
        {"question": "💼 Inserisci la tua PROFESSIONE:", "label": "💼 Professione:", "skippable": False},
        {"question": "📜 Breve descrizione delle competenze (max. 5 righe):", "label": "📜 Competenze:", "skippable": False},
        {"question": "📎 Puoi allegare il file del TUO CURRICULUM (word o pdf):", "label": "📝 Curriculum:", "skippable": True},
        {"question": "🔗 LINK al tuo Profilo LinkedIn:", "label": "🔗 Profilo LinkedIn:", "skippable": True},
        {"question": "📞 Inserisci i tuoi CONTATTI (es. @IlTuoNickTelegram, Telefono, Email..):", "label": "📞 Contatti:", "skippable": False}
    ]
}

POINTER_MESSAGE_IDS = {
    "job": 466,
    "project": 467,
    "event": 463,
    "profile": 468
}

user_data = {}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60),
       retry=retry_if_exception_type((errors.FloodWait, errors.RPCError)))
async def safe_delete(client, chat_id, message_id):
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass

def build_announcement_text(info, user, show_id=None):
    cat = info["category"]
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
    author = f"@{user.username}" if user.username else user.first_name
    text = ""
    if show_id is not None:
        text += f"ID annuncio: {show_id}\n"
    text += f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
    for label, a in info["answers"].items():
        if a != "Saltato.":
            text += f"{label}\n{a}\n\n"
    return text

async def send_preview(client, user_id, info):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
    file_id = info.get("file")
    file_type = info.get("file_type")
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(user_id, file_id, caption=text)
        else:
            msg = await client.send_document(user_id, file_id, caption=text)
    else:
        msg = await client.send_message(user_id, text)
    return msg.id

async def update_preview_with_id(client, user_id, preview_id, info, ann_id):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=ann_id)
    file_id = info.get("file")
    file_type = info.get("file_type")
    try:
        if file_id:
            await client.edit_message_caption(user_id, preview_id, caption=text)
        else:
            await client.edit_message_text(user_id, preview_id, text)
    except Exception as e:
        logging.warning("Impossibile aggiornare la preview con l'ID annuncio.")

async def publish_announcement(client, user_id, info):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=None)  # MAI mostrare l'ID nell'annuncio pubblico
    file_id = info.get("file")
    file_type = info.get("file_type")
    pointer_id = POINTER_MESSAGE_IDS.get(info["category"])
    if file_id:
        if file_type == "photo":
            msg = await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
        else:
            msg = await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
    else:
        msg = await client.send_message(CHAT_ID, text, reply_to_message_id=pointer_id)
    return msg

async def send_clean_message(client, user_id, chat_id, text, reply_markup=None):
    last_msg_id = user_data.get(user_id, {}).get("last_bot_message_id")
    if last_msg_id:
        await safe_delete(client, chat_id, last_msg_id)
    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)
    if user_id not in user_data:
        user_data[user_id] = {"last_bot_message_id": None, "messages_to_delete": []}
    user_data[user_id]["last_bot_message_id"] = sent.id
    user_data[user_id]["messages_to_delete"].append(sent.id)

# ------------------------ HANDLER /start ------------------------

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "step": 0,
        "answers": {},
        "messages_to_delete": [],
        "last_bot_message_id": None,
        "file": None,
        "file_type": None,
        "category": None,
        "preview_msg_id": None,
        "confirm_msg_id": None
    }
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
        [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
        [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
        [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
    ])
    await send_clean_message(client, user_id, message.chat.id, "Benvenuto! Cosa vuoi pubblicare all'interno della Community?", buttons)

# ------------------------ RACCOLTA DATI UTENTE ------------------------

@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        return
    try:
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
            question_data = CATEGORY_QUESTIONS[cat][info["step"]]
            buttons = [
                [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
            ]
            if question_data.get("skippable"):
                buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
            buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
            await send_clean_message(client, user_id, message.chat.id, question_data["question"], InlineKeyboardMarkup(buttons))
        else:
            # Preview privata SENZA ID
            preview_id = await send_preview(client, user_id, info)
            user_data[user_id]["preview_msg_id"] = preview_id
            confirm_btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            confirm_msg = await client.send_message(user_id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
            user_data[user_id]["confirm_msg_id"] = confirm_msg.id
    except Exception as e:
        logging.exception("Errore nella raccolta dati")

# ------------------------ HANDLER CALLBACK ------------------------

@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    try:
        if data.startswith("new_"):
            cat = data.replace("new_", "")
            user_data[user_id].update({"category": cat, "step": 0, "answers": {}, "file": None, "file_type": None})
            await send_clean_message(
                client,
                user_id,
                user_id,
                CATEGORY_QUESTIONS[cat][0]["question"],
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
            )

        elif data == "back_to_menu":
            if user_id in user_data:
                for mid in user_data[user_id].get("messages_to_delete", []):
                    await safe_delete(client, user_id, mid)
                user_data.pop(user_id, None)
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📆 Evento", callback_data="new_event")],
                [InlineKeyboardButton("💼 Annuncio di Lavoro", callback_data="new_job")],
                [InlineKeyboardButton("💡 Call Pubblica per un Progetto", callback_data="new_project")],
                [InlineKeyboardButton("👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
            ])
            await send_clean_message(client, user_id, user_id, "🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?", buttons)

        elif data.startswith("confirm_"):
            uid = int(data.split("_")[1])
            info = user_data[uid]
            msg = await publish_announcement(client, uid, info)
            if msg:
                # Aggiorna la preview con l'ID reale
                preview_id = info.get("preview_msg_id")
                if preview_id:
                    await update_preview_with_id(client, uid, preview_id, info, msg.id)
                # Elimina il messaggio con i bottoni conferma/annulla
                await client.delete_messages(uid, callback_query.message.id)
                # Messaggio di conferma pubblicazione con bottone elimina
                conferma = (
                    f"✅ Annuncio pubblicato!\n"
                    f"ID annuncio: {msg.id}\n"
                    f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
                )
                menu_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=f"delete_{msg.id}_{preview_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(uid, conferma, reply_markup=menu_btn)
                user_data[uid]["confirm_msg_id"] = confirm_msg.id

        elif data.startswith("delete_"):
            try:
                parts = data.split("_")
                ann_id = int(parts[1])
                preview_id = int(parts[2]) if len(parts) > 2 else None
                user = callback_query.from_user
                msg = await client.get_messages(CHAT_ID, ann_id)
                text = msg.text or msg.caption or ""
                author = f"@{user.username}" if user.username else user.first_name
                if author not in text:
                    await callback_query.answer("❌ Non sei l'autore di questo annuncio.", show_alert=True)
                    return
                await client.delete_messages(CHAT_ID, ann_id)
                # Elimina il messaggio di conferma pubblicazione (con bottone elimina)
                await client.delete_messages(user.id, callback_query.message.id)
                # Mostra conferma eliminazione con bottone torna al menù
                menu_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await client.send_message(
                    user.id,
                    f"✅ Annuncio eliminato con successo.\nID annuncio: {ann_id}",
                    reply_markup=menu_btn
                )
                await callback_query.answer("Hai cancellato il tuo annuncio.", show_alert=False)
            except Exception as e:
                logging.exception("Errore eliminazione bottone")
                await callback_query.answer("❌ Errore durante l'eliminazione.", show_alert=True)

        elif data == "back_to_question":
            info = user_data[user_id]
            if info["step"] > 0:
                info["step"] -= 1
                if info["answers"]:
                    info["answers"].popitem()
                for mid in info["messages_to_delete"]:
                    await safe_delete(client, user_id, mid)
                info["messages_to_delete"].clear()
                q = CATEGORY_QUESTIONS[info["category"]][info["step"]]["question"]
                question_data = CATEGORY_QUESTIONS[info["category"]][info["step"]]
                buttons = [
                    [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
                ]
                if question_data.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
                await send_clean_message(
                    client,
                    user_id,
                    user_id,
                    q,
                    InlineKeyboardMarkup(buttons)
                )

        elif data == "skip_question":
            info = user_data[user_id]
            cat = info["category"]
            step = info["step"]
            label_text = CATEGORY_QUESTIONS[cat][step]["label"]
            info["answers"][label_text] = "Saltato."
            info["step"] += 1
            if info["step"] < len(CATEGORY_QUESTIONS[cat]):
                next_question_data = CATEGORY_QUESTIONS[cat][info["step"]]
                next_q = next_question_data["question"]
                buttons = [
                    [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
                ]
                if next_question_data.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
                await send_clean_message(client, user_id, user_id, next_q, InlineKeyboardMarkup(buttons))
            else:
                preview_id = await send_preview(client, user_id, info)
                user_data[user_id]["preview_msg_id"] = preview_id
                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                    [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                confirm_msg = await client.send_message(user_id, "✅ Confermi di voler pubblicare questo annuncio?", reply_markup=confirm_btns)
                user_data[user_id]["confirm_msg_id"] = confirm_msg.id

    except Exception as e:
        logging.exception("Errore nel callback handler")
        await send_clean_message(client, user_id, user_id, f"❌ Errore: {str(e)}")

# ------------------------ ELIMINAZIONE ANNUNCIO DA COMANDO ------------------------

@bot.on_message(filters.command("elimina") & filters.private)
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
        username = f"@{user.username}" if user.username else user.first_name
        testo = msg.text or msg.caption or ""
        if username not in testo:
            await message.reply("❌ Non sei l'autore di questo annuncio e non puoi eliminarlo.")
            return
        await client.delete_messages(CHAT_ID, msg_id)
        await message.reply(f"✅ Annuncio eliminato con successo.\nID annuncio: {msg_id}")
    except Exception as e:
        logging.exception("Errore durante l'eliminazione dell'annuncio con /elimina")
        await message.reply("❌ Errore durante l'eliminazione dell'annuncio.")

# ------------------------ AVVIO BOT ------------------------

if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")