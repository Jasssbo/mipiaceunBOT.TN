import logging
from config import CHAT_ID, GREEN, RED, YELLOW, RESET

# --- Funzione per verificare se l'utente è presente nel gruppo tramite username ---
async def is_user_allowed_by_username(client, user):
    try:
        usernames = set()
        async for member in client.get_chat_members(CHAT_ID):
            if member.user.username:
                usernames.add(member.user.username.lower())
        username = user.username if user.username else user.first_name
        presente = user.username and user.username.lower() in usernames
        if presente is True:
            #logging.info(f"{GREEN}[START CHECK] L'Utente: @{username} E' Presente nel gruppo{RESET}")
            pass
        elif presente is False:
            #logging.info(f"{RED}[START CHECK] L'Utente: {username} NON E' Presente nel gruppo{RESET}")
            pass
        else:
            logging.info(f"{YELLOW}[START USER CHECK] L'Utente: {username} errore imprevisto.{RESET}")
        return presente
    except Exception as e:
        logging.exception(f"{YELLOW}Errore: '{e}' durante il controllo dell'username nel gruppo.{RESET}")
        return False
