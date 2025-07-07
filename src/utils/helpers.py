from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
from pyrogram import errors
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import CHAT_ID
from utils.state import user_data
from questions import CATEGORY_QUESTIONS, POINTER_MESSAGE_IDS

# ---------- Safe delete ----------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=4, max=60),
    retry=retry_if_exception_type((errors.FloodWait, errors.RPCError))
)
async def safe_delete(client, chat_id: int, message_id: int):
    try:
        await client.delete_messages(chat_id, message_id)
    except errors.MessageDeleteForbidden:
        pass


# ---------- Text builders ----------
def build_announcement_text(info: dict, user, show_id: int | None = None) -> str:
    cat = info["category"]
    category_name = {
        "job": "Annuncio di Lavoro",
        "project": "Progetto",
        "event": "Evento",
        "profile": "Profilo"
    }.get(cat, cat.capitalize() if cat else "")

    author = f"@{user.username}" if user.username else user.first_name
    text = f"ID annuncio: {show_id}\n" if show_id is not None else ""
    text += f"Nuovo {category_name}.\nPubblicato da {author}\n\n"

    for label, answer in info["answers"].items():
        if answer != "Saltato.":
            text += f"{label}\n{answer}\n\n"
    return text


# ---------- Preview / publish ----------
async def send_preview(client, user_id: int, info: dict) -> int:
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
    file_id, ftype = info.get("file"), info.get("file_type")

    if file_id:
        if ftype == "photo":
            msg = await client.send_photo(user_id, file_id, caption=text)
        else:
            msg = await client.send_document(user_id, file_id, caption=text)
    else:
        msg = await client.send_message(user_id, text)
    return msg.id


async def update_preview_with_id(client, user_id: int, preview_id: int, info: dict, ann_id: int):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user, show_id=ann_id)
    file_id, ftype = info.get("file"), info.get("file_type")

    try:
        if file_id:
            await client.edit_message_caption(user_id, preview_id, caption=text)
        else:
            await client.edit_message_text(user_id, preview_id, text)
    except Exception:
        logging.warning("Impossibile aggiornare la preview con l'ID annuncio.")


async def publish_announcement(client, user_id: int, info: dict):
    user = await client.get_users(user_id)
    text = build_announcement_text(info, user)
    file_id, ftype = info.get("file"), info.get("file_type")
    pointer_id = POINTER_MESSAGE_IDS.get(info["category"])

    if file_id:
        if ftype == "photo":
            return await client.send_photo(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
        return await client.send_document(CHAT_ID, file_id, caption=text, reply_to_message_id=pointer_id)
    return await client.send_message(CHAT_ID, text, reply_to_message_id=pointer_id)


# ---------- Clean reply ----------
async def send_clean_message(client, user_id: int, chat_id: int, text: str, reply_markup=None):
    last = user_data.get(user_id, {}).get("last_bot_message_id")
    if last:
        await safe_delete(client, chat_id, last)

    sent = await client.send_message(chat_id, text, reply_markup=reply_markup)

    user_data.setdefault(user_id, {
        "last_bot_message_id": None,
        "messages_to_delete": []
    })
    user_data[user_id]["last_bot_message_id"] = sent.id
    user_data[user_id]["messages_to_delete"].append(sent.id)


async def publish_preview_and_confirm(client, user_id: int, info: dict) -> int:
    """
    1) Send private preview (without ID)
    2) Ask for confirmation
    3) Save preview_msg_id and confirm_msg_id in user_data
    4) Return preview_msg_id
    """
    preview_id = await send_preview(client, user_id, info)
    info["preview_msg_id"] = preview_id

    confirm_btns = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Conferma", callback_data=f"confirm_{user_id}")],
        [InlineKeyboardButton(
            "❌ Annulla",  callback_data=f"cancel_{user_id}")],
        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
    ])
    cmsg = await client.send_message(
        user_id,
        "✅ Confermi di voler pubblicare questo annuncio?",
        reply_markup=confirm_btns
    )
    info["confirm_msg_id"] = cmsg.id
    return preview_id
