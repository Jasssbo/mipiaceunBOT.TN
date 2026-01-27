import json
import os
import logging
import asyncio
import tempfile
from datetime import datetime
from config import report_state, report_timeout, bot, CHAT_ID, BLUE, RESET, YELLOW, RED, GREEN
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Percorso del file dei report (assoluto)
REPORTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../reports.json'))

def load_reports():
    """Carica i report dal file JSON."""
    if not os.path.exists(REPORTS_FILE):
        return []
    try:
        with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        logging.error(f"{RED}[REPORT] reports.json corrotto o non valido: {REPORTS_FILE}{RESET}")
        return []

def save_reports(reports):
    """Salva i report nel file JSON."""
    dirpath = os.path.dirname(REPORTS_FILE)
    os.makedirs(dirpath, exist_ok=True)
    
    # Scrittura atomica usando un file temporaneo
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
    reports = load_reports()
    return sum(1 for r in reports if r['reported_user'] == username)

async def ban_user_if_needed(client, username):
    if count_reports_for_user(username) >= 5:
        try:
            await client.kick_chat_member(CHAT_ID, username)
        except Exception as e:
            logging.info(f"{RED}[REPORT] ERRORE {e} NELL'ESPULSIONE DI {username}{RESET}")
            

async def create_timeout_task(client, user_id, report_timeout):
    """Crea un nuovo task di timeout per una segnalazione"""
    # Create and return an asyncio Task that will handle the timeout.
    return client.loop.create_task(timeout_report_state(client, user_id, report_timeout))
async def timeout_report_state(client, user_id, report_timeout):
    """Gestisce il timeout per una segnalazione"""
    await asyncio.sleep(report_timeout)
    if user_id in report_state:
        logging.info(f"[REPORT] Timeout segnalazione per user_id={user_id}")
        # Remove any stored state for this user and notify them.
        # If a timeout task reference exists, cancel it (defensive).
        try:
            if "timeout_task" in report_state.get(user_id, {}):
                try:
                    report_state[user_id]["timeout_task"].cancel()
                except Exception:
                    pass
        except Exception:
            pass

        report_state.pop(user_id, None)
        try:
            await client.send_message(user_id, "⏱️ Tempo scaduto! La segnalazione è stata annullata. Premi di nuovo 'Segnala utente' per riprovare.")
        except Exception:
            # Ignore send errors on timeout
            pass
def is_reporting(client, update, message):
    """Check if the user is in reporting phase.
    This custom filter verifies if the user exists in the report_state dictionary,
    regardless of the specific step they are in.
    
    Args:
        client: Pyrogram client instance (unused)
        update: Telegram update object (unused)
        message: The message to check
    """
    try:
        if not message or not hasattr(message, 'from_user') or not message.from_user:
            return False
            
        user_id = message.from_user.id
        result = user_id in report_state
        
        if result:
            #logging.info(f"[FILTER] is_reporting: TRUE per user_id={user_id}, stato={report_state.get(user_id)}")
            #logging.info(f"{BLUE}[FILTER] is_reporting: TRUE per @{message.from_user.username} (user_id={user_id}){RESET}")
            pass
        
        return result
    except Exception as e:
        logging.exception(f"[FILTER] Errore nel filtro is_reporting: {str(e)}")
        return False


def _get_user_identifier_from_message(message: Message) -> str:
    """Return a stable identifier for the user: username if available, otherwise numeric id as string."""
    if message.from_user and message.from_user.username:
        return message.from_user.username
    return str(message.from_user.id)


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
            logging.info(f"{BLUE}[REPORT] Erase requested by {user_identifier}: removed {removed} reports{RESET}")
        else:
            await message.reply("ℹ️ Non sono state trovate segnalazioni associate al tuo account come segnalatore.")
    except Exception as e:
        logging.exception(f"{YELLOW}[REPORT] Errore durante l'erase_my_data per {user_identifier}: {e}{RESET}")
        await message.reply("❌ Si è verificato un errore durante la cancellazione dei tuoi dati. Riprova più tardi.")

@bot.on_message(filters.private & filters.create(is_reporting), group=1)
async def report_user_handler(client, message: Message):
    user = message.from_user
    username = user.username if user.username else f"user{user.id}"
    """Handler principale per gestire il flusso di segnalazione utente"""
    user_id = message.from_user.id
    state = report_state.get(user_id, {}).get("step")
    
    #logging.info(f"{BLUE}[REPORT-HANDLER] Messaggio ricevuto da user_id={user_id}, testo='{message.text}'{RESET}")
    # Step 1: attesa username
    if state == "awaiting_username":
        ##logging.info(f"{BLUE}[REPORT] Attesa username da segnalare da @{username} (user_id={user_id}){RESET}")

        # Ottieni l'username dal messaggio inoltrato o dal testo
        if message.forward_from and message.forward_from.username:
            reported_username = message.forward_from.username
        elif message.text:
            reported_username = message.text.strip().lstrip("@")
        else:
            await message.reply("❌ Formato non valido. Invia un @username o inoltra un messaggio dell'utente da segnalare.")
            return

        ##logging.info(f"{BLUE}[REPORT] Username ricevuto: '{reported_username}'{RESET}")

        # Validazione username
        if not reported_username or len(reported_username) < 3 or ' ' in reported_username:
            logging.warning(f"{YELLOW}[REPORT] Username non valido da @{username} user_id={user_id}: '{reported_username}'{RESET}")
            await message.reply("❌ Username non valido. Invia un @username valido o inoltra un messaggio dell'utente da segnalare.")
            return

        # Verifica se l'username esiste nel gruppo
        try:
            # Prima verifichiamo se l'username è valido senza il simbolo @
            try:
                chat = await client.get_chat(reported_username)
            except:
                chat = None
                
            if not chat:
                # Proviamo con il simbolo @
                try:
                    chat = await client.get_chat(f"@{reported_username}")
                except:
                    chat = None

            if not chat:
                logging.warning(f"{YELLOW}[REPORT] Username non trovato nel gruppo da @{username} user_id={user_id}: '{reported_username}'{RESET}")
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await message.reply(
                    f"❌ L'username @{reported_username} non esiste o non appartiene a nessun utente nel gruppo.\n\n"
                    "📝 Puoi:\n"
                    "• Inviare subito un altro @username\n"
                    "• Tornare al menù principale",
                    reply_markup=buttons
                )
                return

            # Verifichiamo se l'utente è nel gruppo
            try:
                member = await client.get_chat_member(CHAT_ID, chat.id)
                if not member:
                    raise ValueError("User not in group")
            except Exception as e:
                logging.warning(f"{YELLOW}[REPORT] Username trovato ma non presente nel gruppo: @{username} user_id={user_id}: '{reported_username}'{RESET}")
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
                ])
                await message.reply(
                    f"❌ L'utente @{reported_username} esiste ma non è presente nel gruppo.\n\n"
                    "📝 Puoi:\n"
                    "• Inviare subito un altro @username\n"
                    "• Tornare al menù principale",
                    reply_markup=buttons
                )
                return

        except Exception as e:
            logging.warning(f"{YELLOW}[REPORT] Errore nella verifica dell'username da @{username}: '{reported_username}' - Errore: {str(e)}{RESET}")
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await message.reply(
                f"❌ Non riesco a verificare l'username @{reported_username}. Assicurati che sia corretto.\n\n"
                "📝 Puoi:\n"
                "• Inviare subito un altro @username\n"
                "• Premere 'Riprova' per ricominciare\n"
                "• Tornare al menù principale",
                reply_markup=buttons
            )
            return
            
        # Cancella eventuale timeout precedente
        if "timeout_task" in report_state[user_id]:
            try:
                report_state[user_id]["timeout_task"].cancel()
            except Exception as e:
                logging.error(f"{YELLOW}[REPORT] Errore nella cancellazione del timeout task: {str(e)}{RESET}")
        
        # Crea nuovo stato con nuovo task di timeout
        timeout_task = await create_timeout_task(client, user_id, report_timeout)
        report_state[user_id] = {
            "step": "awaiting_reason", 
            "reported_username": reported_username,
            "timeout_task": timeout_task
        }

        logging.info(f"{BLUE}[REPORT] Passo a attesa motivazione per @{username} -> user_id={user_id}, reported_username={reported_username}{RESET}")

        # Aggiungiamo bottone per annullare anche in questo step
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Annulla segnalazione", callback_data="cancel_report")]
        ])
        
        await message.reply(
            f"✍️ Scrivi una breve spiegazione del motivo della segnalazione per @{reported_username} (almeno 10 caratteri).\n\n"
            f"❌ Puoi annullare in qualsiasi momento premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return
    # Step 2: attesa motivazione
    elif state == "awaiting_reason":
        ##logging.info(f"{BLUE}[REPORT] Attesa motivazione da @{username} -> user_id={user_id}{RESET}")
        
        if not message.text:
            await message.reply("❌ Per favore, invia un messaggio di testo con la motivazione.")
            return
            
        reason = message.text.strip()
        logging.info(f"{BLUE}[REPORT] Motivazione ricevuta da @{username} -> user_id={user_id}: '{reason}'{RESET}")
        
        # Validazione lunghezza
        if not reason or len(reason) < 10:
            logging.warning(f"{YELLOW}[REPORT] Motivazione troppo breve da @{username} -> user_id={user_id}{RESET}")
            await message.reply("❌ Spiegazione troppo breve. Scrivi almeno 10 caratteri sul motivo della segnalazione.")
            return
        
        reported_username = report_state[user_id].get("reported_username")
        if not reported_username:
            logging.error(f"{YELLOW}[REPORT] Username mancante per @{username} -> user_id={user_id}{RESET}")
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await message.reply(
                "❌ Errore: username da segnalare non trovato. Riavvia la procedura.",
                reply_markup=buttons
            )
            report_state.pop(user_id, None)
            return
            
        reporter = message.from_user.username or str(user_id)
        logging.info(f"[REPORT] Salvo segnalazione: User segnalato= @{reported_username}, User segnalatore= @{reporter}, motivo= '{reason}'")

        # Salvataggio e invio della segnalazione
        try:
            reports = add_report(reported_username, reporter, reason)
            logging.info(f"[REPORT] Segnalazione salvata. Totale segnalazioni: {len(reports)}")
            
            # Verifica del ban
            await ban_user_if_needed(client, reported_username)
            
            # Cancella il task di timeout
            if "timeout_task" in report_state[user_id]:
                try:
                    report_state[user_id]["timeout_task"].cancel()
                except Exception:
                    pass
            
            # Rimuovi lo stato e completa
            report_state.pop(user_id, None)
            
            # Rispondi all'utente con bottone per tornare al menu
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await message.reply(
                f"✅ Segnalazione inviata per @{reported_username}! Grazie per aver contribuito a mantenere la community sicura.",
                reply_markup=buttons
            )
            
        except Exception as e:
            logging.exception(f"[REPORT] Errore durante il salvataggio della segnalazione: {str(e)}")
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
            ])
            await message.reply(
                "❌ Si è verificato un errore durante il salvataggio della segnalazione. Riprova più tardi.",
                reply_markup=buttons
            )
            report_state.pop(user_id, None)
        
        return
    
    # Se l'utente è in report_state ma lo stato non è riconosciuto
    else:
        logging.warning(f"[REPORT] Stato non riconosciuto per user_id={user_id}: {state}")
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
        ])
        await message.reply(
            "❌ Stato segnalazione non valido. Riavvia la procedura.",
            reply_markup=buttons
        )
        report_state.pop(user_id, None)
        return
