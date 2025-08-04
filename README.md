
# TNet.WorkBOT


## Descrizione

Bot Telegram per la gestione di annunci, progetti, eventi e profili lavorativi.  
Permette la creazione, la preview, la pubblicazione e l’eliminazione di annunci tramite bottoni e interfaccia guidata.


---

## Requisiti

- Python 3.10 o superiore
- Un bot Telegram e le relative credenziali (API_ID, API_HASH, BOT_TOKEN)


## Come si usa

1. **Configura** il bot:
   - Inserisci i tuoi dati nel file `bot_infos.env` (API_ID, API_HASH, BOT_TOKEN).
   - Se serve, modifica `source/config.py` per il TOKEN del BOT, l'ID del gruppo o altre costanti.

2. **Installa le dipendenze**:
   - Da terminale, esegui:
     ```
     pip install -r requirements.txt
     ```

3. **Avvia il bot**:
   - Da terminale, esegui:
     ```
     python source/main.py
     ```

---


## Dove modificare cosa

- **Configurazione**: `source/config.py` — Token, chat_id, costanti, user_data
- **Moduli principali**: `source/modules/` — Funzionalità core del bot
- **Gestione annunci utente**: `source/modules/user_announcements_interactions/` — Tutto ciò che riguarda la creazione e gestione degli annunci

---


## Struttura

- `source/config.py`: Configurazione generale del bot
- `source/modules/`: Moduli principali
    - `start.py`: Handler per il comando /start
    - `buttons.py`: Gestione dei bottoni inline
    - `collect_data.py`: Gestione domande/risposte utente
    - `topic_guardian.py`: Moderazione dei topic
    - `user_announcements_interactions/`: Moduli per la gestione degli annunci utente
        - `announcement_compiler.py`: Compilazione e gestione degli annunci
        - `collect_data.py`: Raccolta dati dagli utenti per gli annunci
- `source/main.py`: Avvio del bot

---

> Ogni file contiene commenti che spiegano a cosa serve.  
> Se hai dubbi, chiedi pure!