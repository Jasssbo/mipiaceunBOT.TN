import logging
from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.state import user_data
from utils.helpers import (
    send_clean_message, publish_announcement, update_preview_with_id,
    safe_delete, publish_preview_and_confirm
)
from questions import CATEGORY_QUESTIONS
from config import CHAT_ID


def register(app):
    @app.on_callback_query()
    async def callback_handler(client, cq: CallbackQuery):
        data, uid = cq.data, cq.from_user.id

        try:
            # ---------- Category chosen ----------
            if data.startswith("new_"):
                cat = data[4:]
                user_data[uid].update({
                    "category": cat, "step": 0, "answers": {},
                    "file": None, "file_type": None
                })
                await send_clean_message(
                    client, uid, uid,
                    CATEGORY_QUESTIONS[cat][0]["question"],
                    InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Torna al menù",
                                                                callback_data="back_to_menu")]])
                )

            # ---------- Main menu ----------
            elif data == "back_to_menu":
                if uid in user_data:
                    for mid in user_data[uid].get("messages_to_delete", []):
                        await safe_delete(client, uid, mid)
                    user_data.pop(uid, None)

                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "📆 Evento", callback_data="new_event")],
                    [InlineKeyboardButton(
                        "💼 Annuncio di Lavoro", callback_data="new_job")],
                    [InlineKeyboardButton(
                        "💡 Call Pubblica per un Progetto", callback_data="new_project")],
                    [InlineKeyboardButton(
                        "👤 Il Tuo Profilo Lavorativo", callback_data="new_profile")]
                ])

                await send_clean_message(client, uid, uid,
                                         "🏠 Sei tornato al menù principale. Cosa vuoi pubblicare nella Community?",
                                         buttons)

            # ---------- Confirm publish ----------
            elif data.startswith("confirm_"):
                info = user_data[uid]
                msg = await publish_announcement(client, uid, info)
                if not msg:
                    return

                # attach real ID to preview
                await update_preview_with_id(client, uid, info["preview_msg_id"], info, msg.id)

                # delete confirm buttons
                await client.delete_messages(uid, cq.message.id)

                confirm_txt = (
                    f"✅ Annuncio pubblicato!\nID annuncio: {msg.id}\n"
                    f"Puoi eliminare questo annuncio in qualsiasi momento premendo il bottone qui sotto."
                )
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ Elimina questo annuncio",
                                          callback_data=f"delete_{msg.id}_{info['preview_msg_id']}")],
                    [InlineKeyboardButton(
                        "🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                cm = await client.send_message(uid, confirm_txt, reply_markup=buttons)
                info["confirm_msg_id"] = cm.id

            # ---------- Delete via button ----------
            elif data.startswith("delete_"):
                ann_id, preview_id = map(int, data.split("_")[1:3])
                user = cq.from_user
                msg = await client.get_messages(CHAT_ID, ann_id)
                if not msg:
                    await cq.answer("❌ Annuncio non trovato.", show_alert=True)
                    return

                author = f"@{user.username}" if user.username else user.first_name
                body = msg.text or msg.caption or ""
                if author not in body:
                    await cq.answer("❌ Non sei l'autore di questo annuncio.", show_alert=True)
                    return

                await client.delete_messages(CHAT_ID, ann_id)
                await client.delete_messages(uid, cq.message.id)
                await client.send_message(uid, f"✅ Annuncio eliminato con successo.\nID annuncio: {ann_id}",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Torna al menù",
                                                                                                   callback_data="back_to_menu")]]))
                await cq.answer("Hai cancellato il tuo annuncio.", show_alert=False)

            # ---------- Previous question ----------
            elif data == "back_to_question":
                inf = user_data[uid]
                if inf["step"] == 0:
                    return
                inf["step"] -= 1
                if inf["answers"]:
                    inf["answers"].popitem()

                # purge helper msgs
                for mid in inf["messages_to_delete"]:
                    await safe_delete(client, uid, mid)
                inf["messages_to_delete"].clear()

                q_data = CATEGORY_QUESTIONS[inf["category"]][inf["step"]]
                buttons = [[InlineKeyboardButton("⬅️ Torna alla domanda precedente",
                                                 callback_data="back_to_question")]]
                if q_data.get("skippable"):
                    buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda",
                                                            callback_data="skip_question")])
                buttons.append([InlineKeyboardButton("🏠 Torna al menù",
                                                     callback_data="back_to_menu")])

                await send_clean_message(client, uid, uid, q_data["question"],
                                         InlineKeyboardMarkup(buttons))

            # ---------- Skip ----------
            elif data == "skip_question":
                inf = user_data[uid]
                cat, step = inf["category"], inf["step"]
                inf["answers"][CATEGORY_QUESTIONS[cat]
                               [step]["label"]] = "Saltato."
                inf["step"] += 1

                # next or preview
                if inf["step"] < len(CATEGORY_QUESTIONS[cat]):
                    n_q = CATEGORY_QUESTIONS[cat][inf["step"]]
                    buttons = [[InlineKeyboardButton("⬅️ Torna alla domanda precedente",
                                                     callback_data="back_to_question")]]
                    if n_q.get("skippable"):
                        buttons.insert(0, [InlineKeyboardButton("⏭️ Salta questa domanda",
                                                                callback_data="skip_question")])
                    buttons.append([InlineKeyboardButton("🏠 Torna al menù",
                                                         callback_data="back_to_menu")])
                    await send_clean_message(client, uid, uid, n_q["question"],
                                             InlineKeyboardMarkup(buttons))
                else:
                    prev_id = await publish_preview_and_confirm(client, uid, inf)
        except Exception:
            logging.exception("Errore nel callback handler")
            await send_clean_message(client, uid, uid, "❌ Errore interno.")
