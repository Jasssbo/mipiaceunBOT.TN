import json
import os
import logging
import asyncio
from datetime import datetime
from config import report_state, bot, CHAT_ID
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

REPORTS_FILE = os.path.join(os.path.dirname(__file__), '../../reports.json')

def load_reports():
    if not os.path.exists(REPORTS_FILE):
        return []
    with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_reports(reports):
    with open(REPORTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

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
            logging.info(f"[REPORT] ERRORE {e} NELL'ESPULSIONE DI {username}")
            

async def create_timeout_task(client, user_id, timeout=300):
    """Crea un nuovo task di timeout per una segnalazione"""
    return client.loop.create_task(timeout_report_state(client, user_id, timeout))

async def timeout_report_state(client, user_id, timeout=300):
    """Gestisce il timeout per una segnalazione"""
    await asyncio.sleep(timeout)
    if user_id in report_state:
        logging.info(f"[REPORT] Timeout segnalazione per user_id={user_id}")
        report_state.pop(user_id, None)
        try:
            await client.send_message(user_id, "⏱️ Tempo scaduto! La segnalazione è stata annullata. Premi di nuovo 'Segnala utente' per riprovare.")
        except Exception as e:
            logging.error(f"[REPORT] Errore nell'invio del messaggio di timeout: {str(e)}")

def is_reporting(_, __, message):
    """Verifica se l'utente è in fase di segnalazione.
    Questo filtro personalizzato verifica se l'utente è nel dizionario report_state,
    indipendentemente dallo step specifico in cui si trova.
    """
    try:
        if not message or not hasattr(message, 'from_user') or not message.from_user:
            return False
            
        user_id = message.from_user.id
        result = user_id in report_state
        
        if result:
            logging.info(f"[FILTER] is_reporting: TRUE per user_id={user_id}, stato={report_state.get(user_id)}")
        
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

@bot.on_message(filters.private & filters.create(is_reporting) & ~filters.command(["annulla", "Annulla"]) & ~filters.create(is_annulla_text), group=1)
async def report_user_handler(client, message: Message):
    """Handler principale per gestire il flusso di segnalazione utente"""
    user_id = message.from_user.id
    state = report_state.get(user_id, {}).get("step")
    
    logging.info(f"[REPORT-HANDLER] Messaggio ricevuto da user_id={user_id}, testo='{message.text}', stato report_state={report_state.get(user_id)}")
    # Step 1: attesa username
    if state == "awaiting_username":
        logging.info(f"[REPORT] Attesa username da user_id={user_id}")
        
        # Ottieni l'username dal messaggio inoltrato o dal testo
        if message.forward_from and message.forward_from.username:
            reported_username = message.forward_from.username
        elif message.text:
            reported_username = message.text.strip().lstrip("@")
        else:
            await message.reply("❌ Formato non valido. Invia un @username o inoltra un messaggio dell'utente da segnalare.")
            return
            
        logging.info(f"[REPORT] Username ricevuto: '{reported_username}'")
        
        # Validazione username
        if not reported_username or len(reported_username) < 3 or ' ' in reported_username:
            logging.warning(f"[REPORT] Username non valido da user_id={user_id}: '{reported_username}'")
            await message.reply("❌ Username non valido. Invia un @username valido o inoltra un messaggio dell'utente da segnalare.")
            return
            
        # Cancella eventuale timeout precedente
        if "timeout_task" in report_state[user_id]:
            try:
                report_state[user_id]["timeout_task"].cancel()
            except Exception as e:
                logging.error(f"[REPORT] Errore nella cancellazione del timeout task: {str(e)}")
        
        # Crea nuovo stato con nuovo task di timeout
        timeout_task = await create_timeout_task(client, user_id)
        report_state[user_id] = {
            "step": "awaiting_reason", 
            "reported_username": reported_username,
            "timeout_task": timeout_task
        }
        
        logging.info(f"[REPORT] Passo a attesa motivazione per user_id={user_id}, reported_username={reported_username}")
        
        # Aggiungiamo bottone per annullare anche in questo step
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Annulla segnalazione", callback_data="cancel_report")]
        ])
        
        await message.reply(
            f"✍️ Scrivi una breve spiegazione del motivo della segnalazione per @{reported_username} (almeno 10 caratteri).\n\n"
            f"❌ Puoi annullare in qualsiasi momento con /annulla o premendo il bottone qui sotto.",
            reply_markup=buttons
        )
        return
    # Step 2: attesa motivazione
    elif state == "awaiting_reason":
        logging.info(f"[REPORT] Attesa motivazione da user_id={user_id}")
        
        if not message.text:
            await message.reply("❌ Per favore, invia un messaggio di testo con la motivazione.")
            return
            
        reason = message.text.strip()
        logging.info(f"[REPORT] Motivazione ricevuta da user_id={user_id}: '{reason}'")
        
        # Validazione lunghezza
        if not reason or len(reason) < 10:
            logging.warning(f"[REPORT] Motivazione troppo breve da user_id={user_id}")
            await message.reply("❌ Spiegazione troppo breve. Scrivi almeno 10 caratteri sul motivo della segnalazione.")
            return
        
        reported_username = report_state[user_id].get("reported_username")
        if not reported_username:
            logging.error(f"[REPORT] Username mancante per user_id={user_id}")
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
        logging.info(f"[REPORT] Salvo segnalazione: segnalato={reported_username}, segnalatore={reporter}, motivo='{reason}'")
        
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

# Rimosso il debug handler che potrebbe interferire con gli altri handler
    
@bot.on_message((filters.private & filters.command(["annulla", "Annulla"])) | (filters.private & filters.create(is_reporting) & filters.create(is_annulla_text)), group=-1)  # Gruppo -1 per massima priorità
async def annulla_report_handler(client, message: Message):
    """Handler dedicato al comando /annulla o al testo 'annulla', funziona sempre in chat private.
    Group=-1 dà priorità massima a questo handler rispetto agli altri.
    """
    user_id = message.from_user.id
    
    # Logghiamo sempre il comando, per diagnostica
    logging.info(f"[REPORT] Comando di annullamento ricevuto da user_id={user_id}, testo='{message.text}', stato in report_state: {user_id in report_state}")
    
    if user_id in report_state:
        logging.info(f"[REPORT] Annullamento manuale segnalazione per user_id={user_id}")
        
        # Cancella il task di timeout se esiste
        if "timeout_task" in report_state[user_id]:
            try:
                report_state[user_id]["timeout_task"].cancel()
                logging.info(f"[REPORT] Task timeout cancellato per user_id={user_id}")
            except Exception as e:
                logging.error(f"[REPORT] Errore nella cancellazione del timeout task: {str(e)}")
        
        # Rimuovi lo stato e invia conferma
        report_state.pop(user_id, None)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Torna al menù", callback_data="back_to_menu")]
        ])
        await message.reply(
            "❌ Segnalazione annullata. Sei tornato al menù principale.",
            reply_markup=buttons
        )
