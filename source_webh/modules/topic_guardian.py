"""
Handler per controllo e moderazione dei topic (versione webhook).
Elimina messaggi non consentiti nei topic vietati.
"""
import logging
from pyrogram import filters
from config import ALLOWED_TOPIC_IDS, NOT_ALLOWED_TOPIC_IDS, CHAT_ID, GREEN, RED, YELLOW, RESET, bot
from pyrogram.types import Message

@bot.on_message(filters.group)
async def topic_guardian_handler(client, message: Message):
    """
    Handler per moderazione topic.
    In versione webhook: stesso comportamento ma logging migliorato.
    """
    logging.info(f"[TOPIC GUARDIAN] Handler eseguito per message.id={getattr(message, 'id', None)} in chat.id={getattr(message.chat, 'id', None)}")
    
    # Ignora messaggi del bot stesso
    if message.from_user and message.from_user.is_self:
        logging.info("[TOPIC GUARDIAN] Messaggio del bot, ignorato.")
        return

    # Determina topic_id dal messaggio
    topic_id = getattr(message, "message_thread_id", None)
    if topic_id is None and getattr(message, "reply_to_message_id", None):
        topic_id = getattr(message, "reply_to_message_id", None)
    
    # Fallback: estrazione topic_id dal link del messaggio
    if topic_id is None:
        try:
            if hasattr(client, "get_chat_message_link"):
                msg_link = await client.get_chat_message_link(message.chat.id, message.id)
                import re
                match = re.search(r"/([0-9]+)/([0-9]+)$", msg_link)
                if match:
                    topic_id = int(match.group(1))
                else:
                    match = re.search(r"/([0-9]+)$", msg_link)
                    if match:
                        topic_id = int(match.group(1))
        except Exception as e:
            logging.debug(f"[TOPIC GUARDIAN] Errore estrazione topic_id: {e}")

    logging.info(f"[TOPIC GUARDIAN] topic_id rilevato: {topic_id}")

    # Chat generale (nessun topic): consentito
    if topic_id is None:
        logging.info("[TOPIC GUARDIAN] Messaggio permesso: scritto nella chat generale (topic_id=None).")
        return
    
    # Topic vietato: elimina messaggio
    if topic_id in NOT_ALLOWED_TOPIC_IDS:
        logging.info(f"[TOPIC GUARDIAN] Messaggio nel topic vietato: {topic_id}, eliminazione...")
        try:
            await client.delete_messages(message.chat.id, message.id)
            logging.info(f"[TOPIC GUARDIAN] Messaggio {message.id} eliminato dal topic vietato {topic_id}.")
        except Exception as e:
            logging.error(f"[TOPIC GUARDIAN] Errore eliminazione: {e}")
        return
    
    # Topic consentito: permetti
    if topic_id in ALLOWED_TOPIC_IDS:
        logging.info(f"[TOPIC GUARDIAN] Messaggio permesso: scritto nel topic consentito ({topic_id}).")
        return
    
    # Topic non gestito: nessuna azione
    logging.info(f"[TOPIC GUARDIAN] Messaggio in topic non gestito: {topic_id}, nessuna azione.")

    
# --- Funzione per verificare se l'utente è presente nel gruppo tramite username ---
async def is_user_allowed_by_username(client, user):
    """
    Controlla se l'utente (tramite username) è presente tra i membri del gruppo.
    Utile per gestire utenti con username pubblico e verificare la presenza reale.
    Logga il tentativo di interazione.
    
    In versione webhook: stessa logica, nessun cambiamento necessario.
    """
    try:
        usernames = set()
        async for member in client.get_chat_members(CHAT_ID):
            if member.user.username:
                usernames.add(member.user.username.lower())
        
        # Log solo username utente e presenza
        username = user.username if user.username else user.first_name
        presente = user.username and user.username.lower() in usernames
        
        if presente is True:
            logging.info(f"[{GREEN}START CHECK] L'Utente: {username} E' Presente nel gruppo{RESET}")
        elif presente is False:
            logging.info(f"[{RED}START CHECK] L'Utente: {username} NON E' Presente nel gruppo{RESET}")
        else:
            logging.info(f"[{YELLOW}START CHECK] L'Utente: {username} provando a iniziare il bot, ha generato un errore imprevisto.{RESET}")
        
        return presente
    except Exception as e:
        logging.exception(f"{YELLOW}Errore durante il controllo dell'username nel gruppo.{RESET}")
        return False