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

# ------------------------ DOMANDE PER CATEGORIA ------------------------

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

# Messaggi di "puntatore" per rispondere nei topic (Pyrogram non permette di scrivere direttamente nei topic, quindi si risponde a un messaggio fisso)
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
    """Elimina un messaggio, ignorando errori di permesso."""
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass

async def send_clean_message(client, user_id, chat_id, text, reply_markup=None):
    """
    Invia un messaggio e cancella il precedente inviato dal bot all'utente.
    Serve a mantenere la chat privata ordinata e senza messaggi inutili.
    """
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
    """
    Handler per il comando /start: resetta i dati utente e mostra il menù principale.
    """
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

# ------------------------ HANDLER CALLBACK ------------------------

@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """
    Gestisce tutte le interazioni tramite pulsanti inline.
    """
    await callback_query.answer()
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    try:
        # Nuova pubblicazione: resetta i dati e mostra la prima domanda
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

        # Torna al menù principale e pulisce la chat privata
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

        # Conferma o annulla pubblicazione
        elif data.startswith("confirm_") or data.startswith("cancel_"):
            uid = int(data.split("_")[1])
            if data.startswith("confirm_"):
                # Pubblica l'annuncio nel gruppo/canale
                user = await client.get_users(uid)
                username = f"@{user.username}" if user.username else user.first_name
                msg = await publish_announcement(client, uid)
                if msg:
                    info = user_data.get(uid, {})
                    cat = info.get("category")
                    author = username
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
                    conferma = (
                        f"✅ {category_name} pubblicato!\n"
                        f"ID annuncio: {msg.id}\n"
                        f"Pubblicato da: {author}\n\n"
                        f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
                    )
                    # Bottone elimina con callback contenente l'ID del messaggio pubblico e l'ID della preview privata
                    preview_id = user_data[uid].get("preview_msg_id")
                    menu_btn = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🗑️ Elimina questo annuncio", callback_data=f"delete_{msg.id}_{preview_id}")],
                        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                    ])
                    # Invia il messaggio di conferma SENZA aggiungerlo a messages_to_delete!
                    confirm_msg = await client.send_message(uid, conferma, reply_markup=menu_btn)
                    # Salva l'ID del messaggio di conferma per poterlo eliminare dopo
                    user_data[uid]["confirm_msg_id"] = confirm_msg.id
                text = "✅ Pubblicato!"
            else:
                text = "❌ Inserimento annullato."
                # Se annullato, elimina anche l'anteprima
                preview_id = user_data.get(uid, {}).get("preview_msg_id")
                if preview_id:
                    await safe_delete(client, chat_id, preview_id)

            # Elimina tutti i messaggi temporanei tranne l'anteprima (se pubblicato)
            preview_id = user_data.get(uid, {}).get("preview_msg_id")
            for mid in user_data.get(uid, {}).get("messages_to_delete", []):
                if data.startswith("confirm_") and preview_id and mid == preview_id:
                    continue  # NON eliminare l'anteprima se pubblicato
                await safe_delete(client, chat_id, mid)
            user_data[uid]["messages_to_delete"].clear()
            menu_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            if not data.startswith("confirm_"):
                await send_clean_message(client, user_id, chat_id, text, menu_btn)
            user_data.pop(uid, None)

        # Torna alla domanda precedente
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
                    chat_id,
                    q,
                    InlineKeyboardMarkup(buttons)
                )

        # Salta domanda skippabile
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
                await send_clean_message(client, user_id, chat_id, next_q, InlineKeyboardMarkup(buttons))
            else:
                # Mostra anteprima finale
                info = user_data[user_id]
                cat = info["category"]
                user = await client.get_users(user_id)
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
                announcement_text = f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
                for label, a in info["answers"].items():
                    if a != "Saltato.":
                        announcement_text += f"{label}\n{a}\n\n"

                file_id = info.get("file")
                file_type = info.get("file_type")
                if file_id:
                    if file_type == "photo":
                        preview_msg = await client.send_photo(chat_id, file_id, caption=announcement_text)
                    else:
                        preview_msg = await client.send_document(chat_id, file_id, caption=announcement_text)
                else:
                    preview_msg = await client.send_message(chat_id, announcement_text)
                user_data[user_id]["preview_msg_id"] = preview_msg.id

                confirm_btns = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                    [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await send_clean_message(client, user_id, chat_id, "✅ Confermi di voler pubblicare questo annuncio?", confirm_btns)

    except Exception as e:
        logging.exception("Errore nel callback handler")
        await send_clean_message(client, user_id, chat_id, f"❌ Errore: {str(e)}")

# ------------------------ RACCOLTA DATI UTENTE ------------------------

@bot.on_message(filters.private & ~filters.command("start"))
async def collect_data_handler(client, message: Message):
    """
    Gestisce la raccolta delle risposte dell'utente alle domande.
    """
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

        # Gestione allegati (foto/documenti)
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
            # Mostra la domanda successiva
            question_data = CATEGORY_QUESTIONS[cat][info["step"]]
            buttons = [
                [InlineKeyboardButton("⬅️ Torna alla domanda precedente", callback_data="back_to_question")]
            ]
            if question_data.get("skippable"):
                buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda", callback_data="skip_question")])
            buttons.append([InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")])
            await send_clean_message(client, user_id, message.chat.id, question_data["question"], InlineKeyboardMarkup(buttons))
        else:
            # Mostra anteprima finale identica all'annuncio pubblico
            user = await client.get_users(user_id)
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
            announcement_text = f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
            for label, a in info["answers"].items():
                if a != "Saltato.":
                    announcement_text += f"{label}\n{a}\n\n"

            file_id = info.get("file")
            file_type = info.get("file_type")
            if file_id:
                if file_type == "photo":
                    preview_msg = await client.send_photo(message.chat.id, file_id, caption=announcement_text)
                else:
                    preview_msg = await client.send_document(message.chat.id, file_id, caption=announcement_text)
            else:
                preview_msg = await client.send_message(message.chat.id, announcement_text)
            user_data[user_id]["preview_msg_id"] = preview_msg.id

            confirm_btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{user_id}")],
                [InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_{user_id}")],
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await send_clean_message(client, user_id, message.chat.id, "✅ Confermi di voler pubblicare questo annuncio?", confirm_btns)

    except Exception as e:
        logging.exception("Errore nella raccolta dati")

# ------------------------ PUBBLICAZIONE ANNUNCIO ------------------------

async def publish_announcement(client, user_id):
    """
    Pubblica l'annuncio nel gruppo/canale.
    Per privacy e semplicità, non viene usato alcun database: l'autore viene riconosciuto tramite il testo pubblicato.
    """
    info = user_data.get(user_id)
    if not info:
        return

    cat = info["category"]
    user = await client.get_users(user_id)
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
    announcement_text = f"Nuovo {category_name}.\nPubblicato da {author}\n\n"
    for label, a in info["answers"].items():
        if a != "Saltato.":
            announcement_text += f"{label}\n{a}\n\n"

    file_id = info.get("file")
    file_type = info.get("file_type")
    # Pyrogram non permette di pubblicare direttamente nei topic: si risponde a un messaggio fisso (pointer)
    pointer_id = POINTER_MESSAGE_IDS.get(cat)
    try:
        if file_id:
            if file_type == "photo":
                msg = await client.send_photo(CHAT_ID, file_id, caption=announcement_text, reply_to_message_id=pointer_id)
            else:
                msg = await client.send_document(CHAT_ID, file_id, caption=announcement_text, reply_to_message_id=pointer_id)
        else:
            msg = await client.send_message(CHAT_ID, announcement_text, reply_to_message_id=pointer_id)
        return msg
    except Exception as e:
        logging.exception(f"Errore durante la pubblicazione: {e}")
        return None

# ------------------------ ELIMINAZIONE ANNUNCIO ------------------------

@bot.on_message(filters.command("elimina") & filters.private)
async def elimina_annuncio_handler(client, message: Message):
    """
    Permette all'utente di eliminare un proprio annuncio pubblicato.
    Per privacy e semplicità, non viene usato alcun database: il bot verifica che l'autore sia nel testo dell'annuncio.
    """
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
        # L'autore viene riconosciuto dal testo pubblicato, non da un database
        if username not in testo:
            await message.reply("❌ Non sei l'autore di questo annuncio e non puoi eliminarlo.")
            return

        await client.delete_messages(CHAT_ID, msg_id)
        await message.reply("✅ Annuncio eliminato con successo.")
    except Exception as e:
        logging.exception("Errore durante l'eliminazione dell'annuncio con /elimina")
        await message.reply("❌ Errore durante l'eliminazione dell'annuncio.")

# ------------------------ AVVIO BOT ------------------------

if __name__ == "__main__":
    logging.info("🤖 Avvio bot...")
    bot.run()
    logging.info("🔚 Arresto bot...")
