"""
Sistema di segnalazione utenti con protezioni di sicurezza e privacy.
- Traccia segnalazioni per Telegram user ID (non username) per evitare evasione
- Richiede segnalatori unici per l'auto-ban
- Notifica gli admin delle segnalazioni
- Supporta cancellazione completa dei dati (GDPR)
- Applica policy di retention automatica
- Rate limiting per prevenire abusi
"""
import json
import os
import logging
import asyncio
import tempfile
from datetime import datetime, timedelta
from config import (
    report_timeout, bot, CHAT_ID, ADMIN_IDS,
    MAX_REPORTS_PER_DAY, REPORT_RETENTION_DAYS, AUTO_BAN_THRESHOLD
)
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from core.session_manager import get_report_sessions
from core.ui_components import build_back_to_menu_keyboard, build_cancel_report_keyboard

# Get report session manager
report_sessions = get_report_sessions()

# Percorso del file dei report (assoluto)
REPORTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../reports.json'))


# ======================== DATA LAYER ========================

def load_reports():
    """Carica i report dal file JSON."""
    if not os.path.exists(REPORTS_FILE):
        return []
    try:
        with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        logging.error("[REPORT] reports.json corrotto o non valido")
        return []


def save_reports(reports):
    """Salva i report nel file JSON con scrittura atomica."""
    dirpath = os.path.dirname(REPORTS_FILE)
    os.makedirs(dirpath, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dirpath, prefix='reports_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tf:
            json.dump(reports, tf, ensure_ascii=False, indent=2)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_path, REPORTS_FILE)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def add_report(reported_user_id: int, reported_username: str,
               reporter_id: int, reporter_username: str, reason: str):
    """
    Aggiunge un report tracciando per user ID (stabile) con username come display.
    Restituisce la lista aggiornata dei report.
    """
    reports = load_reports()
    reports.append({
        'reported_user_id': reported_user_id,
        'reported_username': reported_username,
        'reporter_id': reporter_id,
        'reporter_username': reporter_username,
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    })
    save_reports(reports)
    return reports


def count_unique_reporters_for_user(user_id: int) -> int:
    """Conta il numero di segnalatori UNICI per un utente (per user ID)."""
    reports = load_reports()
    unique_reporters = set()
    for r in reports:
        if r.get('reported_user_id') == user_id:
            unique_reporters.add(r.get('reporter_id'))
        # Backward compatibility: controlla anche per username
        elif r.get('reported_user') and not r.get('reported_user_id'):
            pass  # Vecchio formato, non contare per auto-ban
    return len(unique_reporters)


def count_reports_today_by_user(reporter_id: int) -> int:
    """Conta quante segnalazioni ha fatto un utente oggi (rate limiting)."""
    reports = load_reports()
    today = datetime.now().date()
    count = 0
    for r in reports:
        if r.get('reporter_id') == reporter_id:
            try:
                report_date = datetime.fromisoformat(r['timestamp']).date()
                if report_date == today:
                    count += 1
            except (ValueError, KeyError):
                pass
    return count


def has_already_reported(reporter_id: int, reported_user_id: int) -> bool:
    """Controlla se un utente ha già segnalato un altro utente."""
    reports = load_reports()
    for r in reports:
        if r.get('reporter_id') == reporter_id and r.get('reported_user_id') == reported_user_id:
            return True
    return False


def apply_retention_policy():
    """Rimuove i report più vecchi della durata di retention configurata."""
    if REPORT_RETENTION_DAYS <= 0:
        return 0

    reports = load_reports()
    cutoff = datetime.now() - timedelta(days=REPORT_RETENTION_DAYS)
    original_len = len(reports)

    filtered = []
    for r in reports:
        try:
            report_time = datetime.fromisoformat(r['timestamp'])
            if report_time > cutoff:
                filtered.append(r)
        except (ValueError, KeyError):
            filtered.append(r)  # Conserva report senza timestamp valido

    removed = original_len - len(filtered)
    if removed > 0:
        save_reports(filtered)
        logging.info(f"[RETENTION] Rimossi {removed} report scaduti (>{REPORT_RETENTION_DAYS} giorni)")
    return removed


# ======================== BAN LOGIC ========================

async def ban_user_if_needed(client, reported_user_id: int, reported_username: str):
    """
    Banna un utente solo se ha ricevuto segnalazioni da almeno AUTO_BAN_THRESHOLD
    utenti UNICI. Notifica gli admin.
    """
    unique_count = count_unique_reporters_for_user(reported_user_id)
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


# ======================== TIMEOUT ========================

async def create_timeout_task(client, user_id, timeout_seconds):
    """Crea un nuovo task di timeout per una segnalazione"""
    return client.loop.create_task(timeout_report_state(client, user_id, timeout_seconds))


async def timeout_report_state(client, user_id, timeout_seconds):
    """Gestisce il timeout per una segnalazione"""
    await asyncio.sleep(timeout_seconds)
    if report_sessions.has_session(user_id):
        logging.info(f"[REPORT] Timeout segnalazione per user_id={user_id}")
        session = report_sessions.get_session(user_id)
        if session and "timeout_task" in session:
            try:
                session["timeout_task"].cancel()
            except Exception:
                pass

        report_sessions.delete_session(user_id)
        try:
            await client.send_message(
                user_id,
                "⏱️ Tempo scaduto! La segnalazione è stata annullata. "
                "Premi di nuovo 'Segnala utente' per riprovare."
            )
        except Exception:
            pass


# ======================== FILTERS ========================

def is_reporting(client, update, message):
    """Filtro custom: verifica se l'utente è in fase di segnalazione."""
    try:
        if not message or not hasattr(message, 'from_user') or not message.from_user:
            return False
        return report_sessions.has_session(message.from_user.id)
    except Exception as e:
        logging.exception(f"[FILTER] Errore nel filtro is_reporting")
        return False


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
        reports = load_reports()

        # Report dove l'utente è il segnalatore
        as_reporter = [r for r in reports
                       if r.get('reporter_id') == user_id
                       or str(r.get('reporter')) == username
                       or str(r.get('reporter')) == str(user_id)]

        # Report dove l'utente è stato segnalato
        as_reported = [r for r in reports
                       if r.get('reported_user_id') == user_id
                       or r.get('reported_user') == username]

        text = "📊 **I TUOI DATI** 📊\n\n"

        if not as_reporter and not as_reported:
            text += "✅ Non abbiamo nessun dato conservato su di te.\n"
        else:
            if as_reporter:
                text += f"📤 **Segnalazioni inviate da te:** {len(as_reporter)}\n"
                for i, r in enumerate(as_reporter, 1):
                    reported = r.get('reported_username', r.get('reported_user', 'N/A'))
                    ts = r.get('timestamp', 'N/A')[:10]
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
        reports = load_reports()
        original_len = len(reports)

        # Rimuovi report dove l'utente è il segnalatore O il segnalato
        filtered = []
        for r in reports:
            is_reporter = (
                r.get('reporter_id') == user_id
                or str(r.get('reporter')) == username
                or str(r.get('reporter')) == str(user_id)
            )
            is_reported = (
                r.get('reported_user_id') == user_id
                or r.get('reported_user') == username
            )
            if not is_reporter and not is_reported:
                filtered.append(r)

        removed = original_len - len(filtered)
        if removed > 0:
            save_reports(filtered)
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

    # Applica la retention policy ad ogni accesso admin
    apply_retention_policy()

    reports = load_reports()
    if not reports:
        await message.reply("✅ Nessuna segnalazione presente.")
        return

    # Mostra le ultime 20 segnalazioni
    recent = reports[-20:]
    text = f"📋 **SEGNALAZIONI** ({len(reports)} totali, ultime {len(recent)}):\n\n"

    for i, r in enumerate(recent, 1):
        reported = r.get('reported_username', r.get('reported_user', 'N/A'))
        reported_id = r.get('reported_user_id', 'N/A')
        reporter = r.get('reporter_username', r.get('reporter', 'N/A'))
        reason = r.get('reason', 'N/A')[:100]  # Tronca per leggibilità
        ts = r.get('timestamp', 'N/A')[:16]
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
        reports = load_reports()
        original_len = len(reports)
        filtered = [r for r in reports if r.get('reported_user_id') != target_id]
        removed = original_len - len(filtered)

        if removed > 0:
            save_reports(filtered)
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

@bot.on_message(filters.private & filters.create(is_reporting), group=1)
async def report_user_handler(client, message: Message):
    """Handler principale per gestire il flusso di segnalazione utente"""
    user = message.from_user
    user_id = user.id
    session = report_sessions.get_session(user_id)
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

        # Rate limiting: controlla quante segnalazioni ha fatto oggi
        today_count = count_reports_today_by_user(user_id)
        if today_count >= MAX_REPORTS_PER_DAY:
            logging.warning(f"[REPORT] Rate limit raggiunto per user_id={user_id} ({today_count} segnalazioni oggi)")
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                f"⚠️ Hai già inviato {today_count} segnalazioni oggi. "
                f"Il limite giornaliero è {MAX_REPORTS_PER_DAY}.\n"
                "Riprova domani.",
                reply_markup=buttons
            )
            report_sessions.delete_session(user_id)
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
        if reported_user_id and has_already_reported(user_id, reported_user_id):
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                f"ℹ️ Hai già segnalato @{reported_username} in precedenza.\n"
                "Non è possibile segnalare lo stesso utente più volte.",
                reply_markup=buttons
            )
            report_sessions.delete_session(user_id)
            return

        # Controlla che non si auto-segnali
        if reported_user_id == user_id:
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                "❌ Non puoi segnalare te stesso.",
                reply_markup=buttons
            )
            report_sessions.delete_session(user_id)
            return

        # Cancella eventuale timeout precedente
        if session and "timeout_task" in session:
            try:
                session["timeout_task"].cancel()
            except Exception:
                pass

        # Crea nuovo stato con nuovo task di timeout
        timeout_task = await create_timeout_task(client, user_id, report_timeout)
        report_sessions.update_session(user_id, {
            "step": "awaiting_reason",
            "reported_username": reported_username,
            "reported_user_id": reported_user_id,
            "timeout_task": timeout_task
        })

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

        session = report_sessions.get_session(user_id)
        reported_username = session.get("reported_username") if session else None
        reported_user_id = session.get("reported_user_id") if session else None

        if not reported_username:
            buttons = build_back_to_menu_keyboard()
            await message.reply(
                "❌ Errore: username da segnalare non trovato. Riavvia la procedura.",
                reply_markup=buttons
            )
            report_sessions.delete_session(user_id)
            return

        reporter_username = user.username or str(user_id)
        logging.info(f"[REPORT] Segnalazione salvata: reporter_id={user_id} -> reported_id={reported_user_id}")

        # Salvataggio e invio della segnalazione
        try:
            reports = add_report(
                reported_user_id=reported_user_id,
                reported_username=reported_username,
                reporter_id=user_id,
                reporter_username=reporter_username,
                reason=reason
            )
            logging.info(f"[REPORT] Segnalazione salvata. Totale: {len(reports)}")

            # Notifica gli admin
            for admin_id in ADMIN_IDS:
                try:
                    await client.send_message(
                        admin_id,
                        f"📨 **Nuova segnalazione**\n"
                        f"Segnalato: @{reported_username} (ID: {reported_user_id})\n"
                        f"Segnalazioni uniche: {count_unique_reporters_for_user(reported_user_id)}/{AUTO_BAN_THRESHOLD}\n\n"
                        f"Usa /admin_reports per i dettagli."
                    )
                except Exception:
                    pass

            # Verifica del ban (ora con segnalatori unici)
            await ban_user_if_needed(client, reported_user_id, reported_username)

            # Cancella il task di timeout
            if session and "timeout_task" in session:
                try:
                    session["timeout_task"].cancel()
                except Exception:
                    pass

            report_sessions.delete_session(user_id)

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
            report_sessions.delete_session(user_id)

        return

    # Se l'utente è in report_sessions ma lo stato non è riconosciuto
    else:
        logging.warning(f"[REPORT] Stato non riconosciuto per user_id={user_id}: {state}")
        buttons = build_back_to_menu_keyboard()
        await message.reply(
            "❌ Stato segnalazione non valido. Riavvia la procedura.",
            reply_markup=buttons
        )
        report_sessions.delete_session(user_id)
        return
