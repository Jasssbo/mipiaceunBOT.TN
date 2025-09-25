"""
Gestione segnalazioni utenti (versione webhook).
Mantiene FileLock per reports.json ma usa Redis per report_state.
"""
import json
import os
import logging
import tempfile
from datetime import datetime
from config import bot, CHAT_ID, get_report_state, set_report_state, delete_report_state
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# File locking for atomic writes (mantenuto come nell'originale)
from filelock import FileLock

# Percorso del file dei report (assoluto)
REPORTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../reports.json'))
REPORTS_LOCK = REPORTS_FILE + '.lock'


def load_reports():
    """Carica i report dal file JSON in modo thread-safe."""
    if not os.path.exists(REPORTS_FILE):
        return []
    lock = FileLock(REPORTS_LOCK)
    with lock:
        with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, ValueError):
                logging.error(f"[REPORT] reports.json corrotto o non valido: {REPORTS_FILE}")
                return []


def save_reports(reports):
    """Salva i report nel file JSON in modo atomico e thread-safe."""
    dirpath = os.path.dirname(REPORTS_FILE)
    os.makedirs(dirpath, exist_ok=True)
    lock = FileLock(REPORTS_LOCK)
    with lock:
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


def add_report(reported_user, reporter, reason):
    """Aggiunge un nuovo report al file JSON."""
    reports = load_reports()
    reports.append({
        'reported_user': reported_user,
        'reporter': reporter,
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    })
    save_reports(reports)
    return reports


def count_reports_for_user(username):
    """Conta il numero di report per un username specifico."""
    reports = load_reports()
    return sum(1 for r in reports if r['reported_user'] == username)


async def ban_user_if_needed(client, username):
    """Banna l'utente se ha raggiunto 5 o più segnalazioni."""
    if count_reports_for_user(username) >= 5:
        try:
            await client.kick_chat_member(CHAT_ID, username)
            logging.info(f"[REPORT] Utente {username} bannato per troppe segnalazioni")
        except Exception as e:
            logging.info(f"[REPORT] ERRORE {e} NELL'ESPULSIONE DI {username}")


# ========== FILTRI PERSONALIZZATI ==========

def is_reporting(_, __, message):
    """
    Verifica se l'utente è in fase di segnalazione.
    In versione webhook: controlla Redis invece della memoria.
    """
    try:
        if not message or not hasattr(message, 'from_user') or not message.from_user:
            return False
            
        user_id = message.from_user.id
        report_data = get_report_state(user_id)
        result = report_data is not None
        
        if result:
            logging.info(f"[FILTER] is_reporting: TRUE per user_id={user_id}, stato={report_data}")
        
        return result
    except Exception as e:
        logging.exception(f"[FILTER] Errore nel filtro is_reporting: {str(e)}")
        return False


def is_annulla_text(_, __, message):
    """Verifica se il messaggio contiene la parola 'annulla' o '/annulla'."""
    try:
        if not message or not message.text:
            return False
            
        text = message.text.lower().strip()
        return text == "annulla" or text == "/annulla" or text == "annulla." or text == "annulla!" or text == "stop"
    except:
        return False


def _get_user_identifier_from_message(message: Message) -> str:
    """Return a stable identifier for the user: username if available, otherwise numeric id as string."""
    if message.from_user and message.from_user.username:
        return message.from_user.username
    return str(message.from_user.id)


# ========== COMMAND HANDLERS ==========

@bot.on_message(filters.private & filters.command(["privacy", "informativa", "informativa_privacy"]))
async def privacy_command_handler(client, message: Message):
    """Send a short privacy notice to the user."""
    text = (
        "Informativa sulla privacy:\n"
        "Conserviamo segnalazioni su file locale (reports.json) per finalità legate alla moderazione.\n"
        "I dati conservati sono: username segnalato, username/id del segnalatore, motivazione e timestamp.\n"
        "Se vuoi che i tuoi dati vengano cancellati, usa /erase_my_data.\n"
        "Per maggiori dettagli consulta i termini con il comando /terms o il maintainer del bot."
    )
    await message.reply(text)


@bot.on_message(filters.private & filters.command(["erase_my_data", "erase", "gdpr_erase"]))
async def erase_my_data_handler(client, message: Message):
    """Erase reports where the requesting user is the reporter (username or id)."""
    user_identifier = _get_user_identifier_from_message(message)
    try:
        reports = load_reports()
        original_len = len(reports)

        # Remove reports where reporter matches username or numeric id
        filtered = [r for r in reports if str(r.get("reporter")) != user_identifier and str(r.get("reporter")) != str(message.from_user.id)]

        removed = original_len - len(filtered)
        if removed > 0:
            save_reports(filtered)
            await message.reply(f"✅ Ho cancellato {removed} segnalazione(i) che ti riguardavano come segnalatore.")
            logging.info(f"[REPORT] Erase requested by {user_identifier}: removed {removed} reports")
        else:
            await message.reply("ℹ️ Non sono state trovate segnalazioni associate al tuo account come segnalatore.")
    except Exception as e:
        logging.exception(f"[REPORT] Errore durante l'erase_my_data per {user_identifier}: {e}")
        await message.reply("❌ Si è verificato un errore durante la cancellazione dei tuoi dati. Riprova più tardi.")


# ========== REPORT FLOW HANDLERS ==========

@bot.on_message(filters.private & filters.create(is_reporting) & ~filters.create(is_annulla_text), group=10)
async def report_user_handler(client, message: Message):
    """
    Gestisce il flusso di segnalazione utente.
    In versione webhook: carica/salva stato da Redis invece della memoria.
    """
    user_id = message.from_user.id
    
    # Carica stato segnalazione da Redis
    report_data = get_report_state(user_id)
    if not report_data:
        logging.warning(f"[REPORT] Stato segnalazione non trovato per user_id={user_id}")
        return
    
    step = report_data.get("step")
    logging.info(f"[REPORT] Processing message from user_id={user_id}, step={step}, text='{message.text[:50] if message.text else 'N/A'}'")
    
    try:
        if step == "awaiting_username":
            # Estrai username dal messaggio
            username = None
            if message.text:
                # Rimuovi @ se presente
                username = message.text.strip().lstrip('@')
            elif message.forward_from:
                username = message.forward_from.username
            
            if not username:
                await message.reply("❌ Per favore invia un @username valido o inoltra un messaggio dell'utente da segnalare.")
                return
            
            # Aggiorna stato con username
            report_data["username"] = username
            report_data["step"] = "awaiting_reason"
            
            # Salva in Redis
            if not set_report_state(user_id, report_data):
                await message.reply("❌ Errore interno. Riprova.")
                return
            
            # Chiedi il motivo
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Annulla segnalazione", callback_data="cancel_report")]
            ])
            await message.reply(
                f"🔎 Hai segnalato: @{username}\n"
                "📝 Ora invia il motivo della segnalazione:",
                reply_markup=buttons
            )
            
        elif step == "awaiting_reason":
            if not message.text:
                await message.reply("❌ Per favore invia il motivo della segnalazione come testo.")
                return
            
            # Recupera dati completi
            username = report_data.get("username")
            reason = message.text.strip()
            reporter = _get_user_identifier_from_message(message)
            
            if not username:
                await message.reply("❌ Errore: username non trovato. Riavvia la segnalazione.")
                delete_report_state(user_id)
                return
            
            # Salva segnalazione nel file
            try:
                add_report(username, reporter, reason)
                logging.info(f"[REPORT] Segnalazione salvata: {username} by {reporter}")
                
                # Controlla se bannare l'utente
                await ban_user_if_needed(client, username)
                
                # Rimuovi stato segnalazione da Redis
                delete_report_state(user_id)
                
                # Conferma all'utente
                await message.reply(
                    f"✅ Segnalazione inviata con successo!\n"
                    f"👤 Utente: @{username}\n"
                    f"📝 Motivo: {reason}"
                )
                
            except Exception as e:
                logging.exception(f"[REPORT] Errore nel salvare segnalazione: {e}")
                await message.reply("❌ Errore nel salvare la segnalazione. Riprova più tardi.")
                
        else:
            logging.warning(f"[REPORT] Step sconosciuto per user_id={user_id}: {step}")
            await message.reply("❌ Errore nel processo di segnalazione. Riavvia con /start.")
            delete_report_state(user_id)
            
    except Exception as e:
        logging.exception(f"[REPORT] Errore nel report handler per user_id={user_id}: {e}")
        await message.reply("❌ Si è verificato un errore. Riprova più tardi.")


@bot.on_message(filters.private & filters.create(is_annulla_text), group=5)
async def annulla_report_handler(client, message: Message):
    """
    Gestisce l'annullamento della segnalazione via comando testuale.
    In versione webhook: rimuove stato da Redis.
    """
    user_id = message.from_user.id
    
    # Controlla se l'utente è in processo di segnalazione
    report_data = get_report_state(user_id)
    if not report_data:
        # Non in segnalazione, ignora
        return
    
    logging.info(f"[REPORT] Annullamento segnalazione via testo per user_id={user_id}")
    
    # Rimuovi stato da Redis
    delete_report_state(user_id)
    
    # Conferma annullamento
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
    ])
    await message.reply(
        "❌ Segnalazione annullata.\n"
        "Puoi tornare al menù principale o avviare una nuova segnalazione.",
        reply_markup=buttons
    )