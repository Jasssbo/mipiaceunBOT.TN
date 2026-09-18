"""
Sistema di segnalazione utenti con protezioni di sicurezza e privacy.
- Traccia segnalazioni per Telegram user ID (non username) per evitare evasione
- Richiede segnalatori unici per l'auto-ban
- Notifica gli admin delle segnalazioni
- Supporta cancellazione completa dei dati (GDPR)
- Applica policy di retention automatica
- Rate limiting per prevenire abusi
"""
import os
import logging
import asyncio
from datetime import datetime, timedelta
from config import (
    report_timeout, bot, CHAT_ID, ADMIN_IDS,
    MAX_REPORTS_PER_DAY, REPORT_RETENTION_DAYS, AUTO_BAN_THRESHOLD
)
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from core.session_manager import get_report_sessions
from core.ui_components import build_back_to_menu_keyboard, build_cancel_report_keyboard
from database.repository import get_repository, async_session, ReportRepository
from database.models import Report

# Get report session manager
report_sessions = get_report_sessions()

# ======================== BAN LOGIC ========================

async def ban_user_if_needed(client, reported_user_id: int, reported_username: str, repo: ReportRepository):
    """
    Banna un utente solo se ha ricevuto segnalazioni da almeno AUTO_BAN_THRESHOLD
    utenti UNICI. Notifica gli admin.
    """
    unique_count = await repo.count_unique_reporters_for_user(reported_user_id)
    if unique_count >= AUTO_BAN_THRESHOLD:
        try:
            await client.ban_chat_member(CHAT_ID, reported_user_id)
            logging.info(f"[AUTO-BAN] Utente user_id={reported_user_id} bannato dopo {unique_count} segnalazioni uniche")

            # Notifica gli admin
            for admin_id in ADMIN_IDS:
                try:
                    await client.send_message(
                        admin_id,
                        f"🚨 AUTO-BAN: L'utente @{reported_username} (ID: {reported_user_id}) "
                        f"è stato bannato automaticamente dopo {unique_count} segnalazioni "
                        f"da utenti unici.\n\n"
                        f"Usa /admin_unban {reported_user_id} per annullare il ban."
                    )
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"[AUTO-BAN] Errore nel ban di user_id={reported_user_id}: {e}")




# ======================== FILTERS ========================


def _get_user_identifier_from_message(message: Message) -> str:
    """Return a stable identifier for the user: username if available, otherwise numeric id as string."""
    if message.from_user and message.from_user.username:
        return message.from_user.username
    return str(message.from_user.id)


# ======================== PRIVACY & GDPR COMMANDS ========================

@bot.on_message(filters.private & filters.command(["privacy", "informativa", "informativa_privacy"]))
async def privacy_command_handler(client, message: Message):
    """Informativa privacy completa per l'utente."""
    text = (
        "🔒 **INFORMATIVA SULLA PRIVACY** 🔒\n\n"
        "mipiaceunBOT è uno strumento della community per aiutare professionisti "
        "creativi a condividere il proprio lavoro e trovare opportunità.\n\n"
        "📋 **Dati che conserviamo:**\n"
        "• Segnalazioni: ID utente segnalato, ID segnalatore, motivazione e data\n"
        "• Gli annunci pubblicati sono visibili nel gruppo Telegram pubblico\n\n"
        "📋 **Dati che NON conserviamo:**\n"
        "• Non salviamo i tuoi messaggi privati con il bot\n"
        "• Non salviamo dati personali al di fuori delle segnalazioni\n"
        "• Le sessioni di compilazione sono temporanee e vengono eliminate\n\n"
        "🔑 **I tuoi diritti:**\n"
        "• /my_data — Vedi tutti i dati che abbiamo su di te\n"
        "• /erase_my_data — Cancella tutti i tuoi dati\n"
        "• /terms — Leggi i termini di servizio\n\n"
        "📧 **Contatti:**\n"
        "Per domande sulla privacy, contatta l'amministratore del gruppo "
        "o apri un issue su GitHub.\n\n"
        "⚖️ Questo servizio opera nel rispetto del GDPR (Regolamento UE 2016/679). "
        "I dati sono trattati esclusivamente per finalità di moderazione della community."
    )
    await message.reply(text)


@bot.on_message(filters.private & filters.command(["terms", "termini", "tos"]))
async def terms_command_handler(client, message: Message):
    """Mostra un riassunto dei termini di servizio."""
    text = (
        "📜 **TERMINI DI SERVIZIO** 📜\n\n"
        "mipiaceunBOT è una piattaforma comunitaria per professionisti creativi.\n\n"
        "✅ **Puoi:**\n"
        "• Pubblicare annunci di lavoro, eventi, progetti e profili\n"
        "• Segnalare comportamenti inappropriati\n"
        "• Richiedere la cancellazione dei tuoi dati\n\n"
        "❌ **Non puoi:**\n"
        "• Pubblicare contenuti illegali, molesti o diffamatori\n"
        "• Impersonare altre persone o professionisti\n"
        "• Pubblicare annunci falsi o ingannevoli\n"
        "• Abusare del sistema di segnalazione\n"
        "• Utilizzare il bot per spam o attività fraudolente\n\n"
        "⚠️ **Responsabilità:**\n"
        "• Sei responsabile delle informazioni che pubblichi\n"
        "• Il bot facilita le connessioni ma non è responsabile "
        "degli accordi tra utenti\n"
        "• Le qualifiche professionali dichiarate non sono verificate dalla piattaforma\n\n"
        "📄 Termini completi: https://github.com/Jasssbo/mipiaceunBOT.TN/blob/main/TERMS_OF_SERVICE.md\n\n"
        "🔒 Per l'informativa privacy: /privacy"
    )
    await message.reply(text)


@bot.on_message(filters.private & filters.command(["my_data", "miei_dati"]))
async def my_data_handler(client, message: Message):
    """Mostra all'utente tutti i dati conservati che lo riguardano."""
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    try:
        async with async_session() as session:
            repo = ReportRepository(session)
            reports = await repo.get_reports_for_user(user_id)

            as_reporter = [r for r in reports if r.reporter_user_id == user_id]
            as_reported = [r for r in reports if r.reported_user_id == user_id]

            text = "📊 **I TUOI DATI** 📊\n\n"

            if not as_reporter and not as_reported:
                text += "✅ Non abbiamo nessun dato conservato su di te.\n"
            else:
                if as_reporter:
                    text += f"📤 **Segnalazioni inviate da te:** {len(as_reporter)}\n"
                    for i, r in enumerate(as_reporter, 1):
                        reported = r.reported_username or 'N/A'
                        ts = str(r.timestamp)[:10] if r.timestamp else 'N/A'
                        text += f"  {i}. @{reported} — {ts}\n"
                    text += "\n"

                if as_reported:
                    text += f"📥 **Segnalazioni ricevute:** {len(as_reported)}\n"
                    text += "  (I dettagli delle segnalazioni non vengono mostrati per proteggere i segnalatori)\n\n"

            text += "\n🗑️ Usa /erase_my_data per cancellare tutti i tuoi dati."
            await message.reply(text)

    except Exception as e:
        logging.exception(f"[REPORT] Errore durante my_data per user_id={user_id}")
        await message.reply("❌ Si è verificato un errore. Riprova più tardi.")


@bot.on_message(filters.private & filters.command(["erase_my_data", "erase", "gdpr_erase"]))
async def erase_my_data_handler(client, message: Message):
    """
    Cancella TUTTI i dati dell'utente: sia come segnalatore che come segnalato.
    Implementa il diritto alla cancellazione GDPR (Art. 17).
    """
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    try:
        async with async_session() as session:
            repo = ReportRepository(session)
            removed = await repo.erase_user_data(user_id)
            
            if removed > 0:
                await message.reply(
                    f"✅ Ho cancellato {removed} record che ti riguardavano.\n\n"
                    "📝 Nota: gli annunci già pubblicati nel gruppo restano visibili "
                    "su Telegram. Per eliminarli, usa il bottone 'Elimina annuncio' "
                    "se ancora disponibile, oppure contatta un amministratore."
                )
                logging.info(f"[GDPR] Erase completato per user_id={user_id}: {removed} record rimossi")
            else:
                await message.reply(
                    "ℹ️ Non sono stati trovati dati associati al tuo account.\n\n"
                    "📝 Se hai annunci pubblicati nel gruppo che vuoi rimuovere, "
                    "usa il bottone 'Elimina annuncio' o contatta un amministratore."
                )
    except Exception as e:
        logging.exception(f"[REPORT] Errore durante erase_my_data per user_id={user_id}")
        await message.reply("❌ Si è verificato un errore durante la cancellazione. Riprova più tardi.")


# ======================== ADMIN COMMANDS ========================

@bot.on_message(filters.private & filters.command(["admin_reports", "admin_segnalazioni"]))
async def admin_reports_handler(client, message: Message):
    """Mostra le segnalazioni agli admin."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ Non hai i permessi per usare questo comando.")
        return

    try:
        async with async_session() as session:
            repo = ReportRepository(session)
            
            # Applica la retention policy ad ogni accesso admin
            if REPORT_RETENTION_DAYS > 0:
                removed = await repo.apply_retention_policy(REPORT_RETENTION_DAYS)
                if removed > 0:
                    logging.info(f"[RETENTION] Rimossi {removed} report scaduti (>{REPORT_RETENTION_DAYS} giorni)")
            
            reports = await repo.get_recent_reports(20)
            total = await repo.get_total_count()
            
            if not reports:
                await message.reply("✅ Nessuna segnalazione presente.")
                return

            text = f"📋 **SEGNALAZIONI** ({total} totali, ultime {len(reports)}):\n\n"

            for i, r in enumerate(reversed(reports), 1):
                reported = r.reported_username or 'N/A'
                reported_id = r.reported_user_id or 'N/A'
                reporter = r.reporter_username or 'N/A'
                reason = r.reason[:100] if r.reason else 'N/A'
                ts = str(r.timestamp)[:16] if r.timestamp else 'N/A'
                text += (
                    f"**{i}.** @{reported} (ID: {reported_id})\n"
                    f"   Segnalato da: @{reporter}\n"
                    f"   Motivo: {reason}\n"
                    f"   Data: {ts}\n\n"
                )

            text += (
                "📌 **Comandi disponibili:**\n"
                "/admin_ban [user_id] — Banna un utente\n"
                "/admin_unban [user_id] — Sbanna un utente\n"
                "/admin_clear_reports [user_id] — Cancella segnalazioni per un utente"
            )

            await message.reply(text)
    except Exception as e:
        logging.error(f"[ADMIN] Errore in admin_reports: {e}")
        await message.reply("❌ Errore durante il caricamento delle segnalazioni.")

@bot.on_message(filters.private & filters.command(["admin_ban"]))
async def admin_ban_handler(client, message: Message):
    """Permette agli admin di bannare un utente manualmente."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ Non hai i permessi per usare questo comando.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Uso: /admin_ban [user_id]\nEsempio: /admin_ban 123456789")
        return

    try:
        target_id = int(parts[1])
        await client.ban_chat_member(CHAT_ID, target_id)
        logging.info(f"[ADMIN] Ban manuale di user_id={target_id} da admin user_id={message.from_user.id}")
        await message.reply(f"✅ Utente {target_id} bannato dal gruppo.")
    except ValueError:
        await message.reply("❌ ID utente non valido. Deve essere un numero.")
    except Exception as e:
        logging.error(f"[ADMIN] Errore nel ban di user_id={parts[1]}: {e}")
        await message.reply(f"❌ Errore durante il ban. L'utente potrebbe non essere nel gruppo.")


@bot.on_message(filters.private & filters.command(["admin_unban"]))
async def admin_unban_handler(client, message: Message):
    """Permette agli admin di sbannare un utente."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ Non hai i permessi per usare questo comando.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Uso: /admin_unban [user_id]\nEsempio: /admin_unban 123456789")
        return

    try:
        target_id = int(parts[1])
        await client.unban_chat_member(CHAT_ID, target_id)
        logging.info(f"[ADMIN] Unban di user_id={target_id} da admin user_id={message.from_user.id}")
        await message.reply(f"✅ Utente {target_id} sbannato. Può rientrare nel gruppo.")
    except ValueError:
        await message.reply("❌ ID utente non valido. Deve essere un numero.")
    except Exception as e:
        logging.error(f"[ADMIN] Errore nell'unban di user_id={parts[1]}: {e}")
        await message.reply(f"❌ Errore durante lo sban.")


@bot.on_message(filters.private & filters.command(["admin_clear_reports"]))
async def admin_clear_reports_handler(client, message: Message):
    """Permette agli admin di cancellare tutte le segnalazioni per un utente."""
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ Non hai i permessi per usare questo comando.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Uso: /admin_clear_reports [user_id]\nEsempio: /admin_clear_reports 123456789")
        return

    try:
        target_id = int(parts[1])
        async with async_session() as session:
            repo = ReportRepository(session)
            removed = await repo.clear_user_reports(target_id)

            if removed > 0:
                logging.info(f"[ADMIN] Cancellate {removed} segnalazioni per user_id={target_id} da admin user_id={message.from_user.id}")
                await message.reply(f"✅ Cancellate {removed} segnalazioni per l'utente {target_id}.")
            else:
                await message.reply(f"ℹ️ Nessuna segnalazione trovata per l'utente {target_id}.")
    except ValueError:
        await message.reply("❌ ID utente non valido. Deve essere un numero.")
    except Exception as e:
        logging.error(f"[ADMIN] Errore nella cancellazione report per {parts[1]}: {e}")
        await message.reply("❌ Errore durante la cancellazione.")


# ======================== REPORT FLOW HANDLER ========================

@bot.on_message(filters.private, group=1)
async def report_user_handler(client, message: Message):
    """Handler principale per gestire il flusso di segnalazione utente"""
    user = message.from_user
    user_id = user.id
    if not await report_sessions.has_session(user_id):
        return
        
    session = await report_sessions.get_session(user_id)
    state = session.get("step") if session else None

    # Step 1: attesa username
    if state == "awaiting_username":

        # Ottieni l'username dal messaggio inoltrato o dal testo
        if message.forward_from and message.forward_from.username:
            reported_username = message.forward_from.username
            reported_user_id_from_forward = message.forward_from.id
        elif message.text:
            reported_username = message.text.strip().lstrip("@")
            reported_user_id_from_forward = None
        else:
            await message.reply("❌ Formato non valido. Invia un @username o inoltra un messaggio dell'utente da segnalare.")
            return

        # Validazione username
        if not reported_username or len(reported_username) < 3 or ' ' in reported_username:
            logging.warning(f"[REPORT] Username non valido ricevuto da user_id={user_id}")
            await message.reply("❌ Username non valido. Invia un @username valido o inoltra un messaggio dell'utente da segnalare.")
            return

        async with async_session() as db_session:
            repo = ReportRepository(db_session)
            
            # Rate limiting: controlla quante segnalazioni ha fatto oggi
            today_count = await repo.count_reports_today_by_user(user_id)
            if today_count >= MAX_REPORTS_PER_DAY:
                logging.warning(f"[REPORT] Rate limit raggiunto per user_id={user_id} ({today_count} segnalazioni oggi)")
                buttons = build_back_to_menu_keyboard()
                await message.reply(
                    f"⚠️ Hai già inviato {today_count} segnalazioni oggi. "
                    f"Il limite giornaliero è {MAX_REPORTS_PER_DAY}.\n"
                    "Riprova domani.",
                    reply_markup=buttons
                )
                await report_sessions.delete_session(user_id)
                return

            # Verifica se l'username esiste nel gruppo
            reported_user_id = reported_user_id_from_forward
            try:
                try:
                    chat = await client.get_chat(reported_username)
                except Exception:
                    chat = None

                if not chat:
                    try:
                        chat = await client.get_chat(f"@{reported_username}")
                    except Exception:
                        chat = None

                if not chat:
                    logging.warning(f"[REPORT] Username non trovato: '{reported_username}' (da user_id={user_id})")
                    buttons = build_back_to_menu_keyboard()
                    await message.reply(
                        f"❌ L'username @{reported_username} non esiste o non appartiene a nessun utente nel gruppo.\n\n"
                        "📝 Puoi:\n"
                        "• Inviare subito un altro @username\n"
                        "• Tornare al menù principale",
                        reply_markup=buttons
                    )
                    return

                reported_user_id = chat.id

                # Verifichiamo se l'utente è nel gruppo
                try:
                    member = await client.get_chat_member(CHAT_ID, chat.id)
                    if not member:
                        raise ValueError("User not in group")
                except Exception:
                    buttons = build_back_to_menu_keyboard()
                    await message.reply(
                        f"❌ L'utente @{reported_username} esiste ma non è presente nel gruppo.\n\n"
                        "📝 Puoi:\n"
                        "• Inviare subito un altro @username\n"
                        "• Tornare al menù principale",
                        reply_markup=buttons
                    )
                    return

            except Exception as e:
                logging.warning(f"[REPORT] Errore verifica username '{reported_username}': {e}")
                buttons = build_back_to_menu_keyboard()
                await message.reply(
                    f"❌ Non riesco a verificare l'username @{reported_username}. Assicurati che sia corretto.\n\n"
                    "📝 Puoi:\n"
                    "• Inviare subito un altro @username\n"
                    "• Tornare al menù principale",
                    reply_markup=buttons
                )
                return

            # Controlla se ha già segnalato questo utente
            if reported_user_id:
                has_reported = await repo.has_already_reported(user_id, reported_user_id)
                if has_reported:
                    buttons = build_back_to_menu_keyboard()
                    await message.reply(
                        f"ℹ️ Hai già segnalato @{reported_username} in precedenza.\n"
                        "Non è possibile segnalare lo stesso utente più volte.",
                        reply_markup=buttons
                    )
                    await report_sessions.delete_session(user_id)
                    return

        # Controlla che non si auto-segnali
        if reported_user_id == user_id:
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                "❌ Non puoi segnalare te stesso.",
                reply_markup=buttons
            )
            await report_sessions.delete_session(user_id)
            return

        # Crea nuovo stato con nuovo task di timeout
        timeout_task = await create_timeout_task(client, user_id, report_timeout)
        await report_sessions.update_session(user_id, {
            "step": "awaiting_reason",
            "reported_username": reported_username,
            "reported_user_id": reported_user_id
        })
        await report_sessions.schedule_cleanup(user_id, report_timeout)

        logging.info(f"[REPORT] user_id={user_id} procede alla motivazione per reported_user_id={reported_user_id}")

        buttons = build_cancel_report_keyboard()
        await message.reply(
            f"✍️ Scrivi una breve spiegazione del motivo della segnalazione per @{reported_username} (almeno 10 caratteri).\n\n"
            f"❌ Puoi annullare in qualsiasi momento premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return

    # Step 2: attesa motivazione
    elif state == "awaiting_reason":
        if not message.text:
            await message.reply("❌ Per favore, invia un messaggio di testo con la motivazione.")
            return

        reason = message.text.strip()

        # Validazione lunghezza
        if not reason or len(reason) < 10:
            await message.reply("❌ Spiegazione troppo breve. Scrivi almeno 10 caratteri sul motivo della segnalazione.")
            return

        if len(reason) > 1000:
            await message.reply("❌ Motivazione troppo lunga. Massimo 1000 caratteri.")
            return

        session = await report_sessions.get_session(user_id)
        reported_username = session.get("reported_username") if session else None
        reported_user_id = session.get("reported_user_id") if session else None

        if not reported_username:
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                "❌ Errore: username da segnalare non trovato. Riavvia la procedura.",
                reply_markup=buttons
            )
            await report_sessions.delete_session(user_id)
            return

        reporter_username = user.username or str(user_id)
        logging.info(f"[REPORT] Segnalazione salvata: reporter_id={user_id} -> reported_id={reported_user_id}")

        # Salvataggio e invio della segnalazione
        try:
            async with async_session() as db_session:
                repo = ReportRepository(db_session)
                report = Report(
                    reported_username=reported_username,
                    reported_user_id=reported_user_id,
                    reporter_username=reporter_username,
                    reporter_user_id=user_id,
                    reason=reason
                )
                await repo.add(report)
                
                unique_reporters = await repo.count_unique_reporters_for_user(reported_user_id)
                logging.info(f"[REPORT] Segnalazione salvata. Segnalatori unici: {unique_reporters}")

                # Notifica gli admin
                for admin_id in ADMIN_IDS:
                    try:
                        await client.send_message(
                            admin_id,
                            f"📨 **Nuova segnalazione**\n"
                            f"Segnalato: @{reported_username} (ID: {reported_user_id})\n"
                            f"Segnalazioni uniche: {unique_reporters}/{AUTO_BAN_THRESHOLD}\n\n"
                            f"Usa /admin_reports per i dettagli."
                        )
                    except Exception:
                        pass

                # Verifica del ban (ora con segnalatori unici)
                await ban_user_if_needed(client, reported_user_id, reported_username, repo)

            await report_sessions.delete_session(user_id)

            buttons = build_back_to_menu_keyboard()
            await message.reply(
                f"✅ Segnalazione inviata per @{reported_username}! "
                "Grazie per aver contribuito a mantenere la community sicura.",
                reply_markup=buttons
            )

        except Exception as e:
            logging.exception(f"[REPORT] Errore durante il salvataggio della segnalazione")
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                "❌ Si è verificato un errore durante il salvataggio della segnalazione. Riprova più tardi.",
                reply_markup=buttons
            )
            await report_sessions.delete_session(user_id)

        return

    # Se l'utente è in report_sessions ma lo stato non è riconosciuto
    else:
        logging.warning(f"[REPORT] Stato non riconosciuto per user_id={user_id}: {state}")
        buttons = build_back_to_menu_keyboard()
        await message.reply(
            "❌ Stato segnalazione non valido. Riavvia la procedura.",
            reply_markup=buttons
        )
        await report_sessions.delete_session(user_id)
        return
