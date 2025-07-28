# TNet.WorkBOT

## Descrizione

Bot Telegram per la gestione di annunci, progetti, eventi e profili lavorativi.  
Permette la creazione, la preview, la pubblicazione e l’eliminazione di annunci tramite bottoni e interfaccia guidata.

---

## Come si usa

1. **Configura** il bot:
   - Inserisci i tuoi dati nel file `bot_infos.env` (API_ID, API_HASH, BOT_TOKEN).
   - Se serve, modifica `src/config.py` per l'ID del gruppo o altre costanti.

2. **Installa le dipendenze**:
   - Da terminale, esegui:
     ```
     pip install -r requirements.txt
     ```

3. **Avvia il bot**:
   - Da terminale, esegui:
     ```
     python src/main.py
     ```

---

## Dove modificare cosa

- **Configurazione**: `src/config.py`
- **Handler dei bottoni/comandi**: `src/handlers/`
- **Funzioni di utilità**: `src/utils/`

---

## Struttura

- `src/config.py`: Configurazione bot (token, chat_id, costanti, user_data)
- `src/handlers/`: Tutti i bottoni e le risposte agli utenti
    - `start.py`: Handler per /start
    - `collect_data.py`: Gestione domande/risposte utente
    - `callback.py`: Gestione bottoni inline
    - `topic_guardian.py`: Moderazione dei topic
- `src/utils/`: Funzioni di utilità (annunci, stato utente, ecc.)
    - `announcement.py`: Funzioni per annunci, preview, pubblicazione, permessi
- `src/main.py`: Avvio del bot

---

> Ogni file contiene commenti che spiegano a cosa serve.  
> Se hai dubbi, chiedi pure!
