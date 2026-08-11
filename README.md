# mipiaceunBOT - Piattaforma Comunitaria per Professionisti Creativi

![Version](https://img.shields.io/badge/versione-1.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/licenza-AGPL--3.0-yellow)

## 📑 Panoramica

**mipiaceunBOT** è un assistente Telegram progettato per facilitare la comunicazione e la collaborazione all'interno di comunità creative e professionali. Il bot permette agli utenti di pubblicare e gestire:

- 📆 **Eventi** - Condividere informazioni su eventi, workshop, conferenze
- 💼 **Annunci di lavoro** - Pubblicare opportunità lavorative o ricerche di collaborazioni
- 💡 **Call pubbliche per progetti** - Proporre progetti collaborativi e cercare professionisti
- 👤 **Profili professionali** - Presentarsi alla community con le proprie competenze

Il bot gestisce il flusso di creazione degli annunci con un'interfaccia intuitiva e semplice, garantendo che tutte le informazioni necessarie vengano raccolte prima della pubblicazione nei canali appropriati.

## 🌟 Funzionalità

### Sistema di pubblicazione guidato
- Interfaccia a bottoni per semplificare la navigazione
- Form interattivi per raccogliere tutte le informazioni necessarie
- Supporto per l'upload di immagini, documenti e collegamenti
- Anteprima dell'annuncio prima della pubblicazione

### Organizzazione della community
- Pubblicazione automatica nei topic appropriati del gruppo
- Protezione dei topic 
- Sistema di moderazione con possibilità di segnalare utenti problematici

### Sicurezza e moderazione
- Verifica che gli utenti siano membri del gruppo
- Sistema di segnalazione per contenuti inappropriati
- Timeout automatici per le interazioni incomplete

## 🛠️ Requisiti tecnici

- **Python 3.10 o superiore**
- **Librerie Python**:
  - pyrogram
  - python-dotenv
  - asyncio
  - Altri (vedi `requirements.txt`)
- **Credenziali Telegram**:
  - API_ID e API_HASH ottenuti da https://my.telegram.org
  - BOT_TOKEN ottenuto da [@BotFather](https://t.me/BotFather)

## 🔧 Configurazione e installazione

### 1. Clonare il repository
```bash
git clone https://github.com/Jasssbo/mipiaceunBOT.TN.git
cd mipiaceunBOT
```

### 2. Installare le dipendenze
```bash
pip install -r requirements.txt
```

### 3. Configurare le credenziali
Crea un file `bot_infos.env` nella directory principale con:
```
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

### 4. Personalizzare la configurazione
Modifica `source/config.py` per:
- Impostare l'ID della chat del gruppo
- Configurare i topic e i messaggi di riferimento
- Personalizzare le domande per i vari tipi di annuncio

### 5. Avviare il bot
```bash
python source/main.py
```

## 📂 Struttura del progetto

- `source/config.py`: Configurazione del bot e costanti
- `source/main.py`: Punto di ingresso dell'applicazione
- `source/modules/`: Moduli funzionali principali
  - `buttons.py`: Gestione dei bottoni inline e callback
  - `start.py`: Handler per il comando /start
  - `topic_guardian.py`: Protezione e moderazione dei topic
- `source/modules/user_announcements_interactions/`: Gestione degli annunci
  - `announcement_compiler.py`: Composizione e pubblicazione annunci
  - `collect_data.py`: Raccolta informazioni dagli utenti
  - `report_user.py`: Sistema di segnalazione utenti

## 🤝 Utilizzo

1. Avvia il bot con `/start`
2. Seleziona il tipo di contenuto che desideri pubblicare
3. Segui le domande guidate fornendo le informazioni richieste
4. Visualizza l'anteprima del tuo annuncio
5. Conferma per pubblicare o modifica se necessario

## 🔒 Privacy e sicurezza

- Il bot registra solamente i dati necessari al suo funzionamento
- I dati degli utenti non vengono condivisi con terze parti
- Le segnalazioni vengono gestite in modo confidenziale
- Fare riferimento al file `TERMS_OF_SERVICE.md` per le condizioni d'uso complete

## 📄 Licenza

Questo progetto è distribuito con licenza GNU Affero General Public License v3.0 (AGPL-3.0). Vedere il file `LICENSE` per dettagli.

La licenza AGPL garantisce che:
- Il codice sorgente rimanga aperto e accessibile
- Chiunque modifichi il bot e lo offra come servizio debba rilasciare il codice sorgente modificato
- Il tuo lavoro venga riconosciuto e attribuito correttamente

## 👥 Contributori

- [@Jasssbo](https://github.com/Jasssbo) - Sviluppatore principale

## 📞 Contatti

Per segnalazioni, problemi o suggerimenti, apri un issue su GitHub o contatta l'amministratore del gruppo Telegram.

---

**Nota**: Questo bot è stato creato per facilitare la comunicazione all'interno di comunità creative e professionali. Qualsiasi utilizzo improprio o per scopi non conformi ai termini di servizio è proibito.
