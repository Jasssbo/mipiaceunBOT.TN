# mipiaceunBOT - Piattaforma Comunitaria per Professionisti Creativi

![Version](https://img.shields.io/badge/versione-2.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)
![License](https://img.shields.io/badge/licenza-AGPL--3.0-yellow)

## 📑 Panoramica

**mipiaceunBOT** è un assistente Telegram asincrono progettato per facilitare la comunicazione e la collaborazione all'interno di comunità creative e professionali. Il bot permette agli utenti di pubblicare e gestire:

- 📆 **Eventi** - Condividere informazioni su eventi, workshop, conferenze
- 💼 **Annunci di lavoro** - Pubblicare opportunità lavorative o ricerche di collaborazioni
- 💡 **Call pubbliche per progetti** - Proporre progetti collaborativi e cercare professionisti
- 👤 **Profili professionali** - Presentarsi alla community con le proprie competenze

Il bot gestisce il flusso di creazione degli annunci con un'interfaccia a bottoni InlineKeyboard intuitiva e sicura. L'architettura è costruita per prevenire memory leak e crash grazie a un solido sistema di gestione dello stato basato su Redis.

## 🌟 Funzionalità Principali

### 1. Sistema di Pubblicazione Guidato e Sicuro
- Moduli di navigazione a bottoni (`InlineKeyboardMarkup`) completamente asincroni.
- Form interattivi protetti da timeout (TTL gestito nativamente via Redis).
- Protezione nativa anti-spam (FloodWait interception) a livello globale.

### 2. Architettura Dati e Moderazione
- **Redis Sessions**: Memorizza gli stati di compilazione in memoria temporanea con TTL (Time-To-Live).
- **SQLite (aiosqlite) + SQLAlchemy**: Memorizza in modo permanente lo storico delle segnalazioni per limitare gli abusi.
- **Sistema di Segnalazione Utenti**: Gli utenti possono segnalare malintenzionati tramite `/report` o bottoni inline.
- **Auto-Ban**: Sistema di limitazione che banna gli utenti dopo un determinato numero di segnalazioni da utenti unici.

## 🛠️ Requisiti Tecnici

- **Python 3.10 o superiore**
- **Redis Server** (per il session management in-memory)
- **Credenziali Telegram**:
  - `API_ID` e `API_HASH` da https://my.telegram.org
  - `BOT_TOKEN` da [@BotFather](https://t.me/BotFather)

## 🔧 Installazione tramite Docker (Consigliata)

L'utilizzo di `docker-compose` assicura che il bot e il server Redis vengano avviati insieme con un solo comando, garantendo isolamento e stabilità.

### 1. Clonare il repository
```bash
git clone https://github.com/Jasssbo/mipiaceunBOT.TN.git
cd mipiaceunBOT
```

### 2. Configurare le credenziali
Crea un file `bot_infos.env` nella directory principale (assicurati che sia ignorato dal version control):
```env
API_ID=il_tuo_api_id
API_HASH=il_tuo_api_hash
BOT_TOKEN=il_tuo_bot_token
ADMIN_IDS=12345678,87654321
CHAT_ID=-1001234567890
```

### 3. Avviare con Docker Compose
```bash
docker-compose up -d --build
```
Il bot e Redis saranno ora operativi in background. Usa `docker-compose logs -f` per leggere i log.

## 📂 Struttura dell'Architettura (Refactored)

La struttura del progetto segue rigidi principi di Clean Architecture e separazione dei ruoli (SoC):

- `source/main.py`: Entry point dell'applicazione asincrona.
- `source/config.py`: Configurazioni generali e dizionario delle domande (DOM).
- `source/core/`:
  - `session_manager.py`: Interfaccia astratta verso il server **Redis**.
  - `ui_components.py`: Generazione dei bottoni InlineKeyboard.
- `source/database/`:
  - `models.py` e `repository.py`: Motore ORM **SQLAlchemy** per il database persistente `users_data.db`.
- `source/middleware/`:
  - `permissions.py`: Decoratori di sicurezza (`@require_group_member`).
- `source/modules/`:
  - `core/`: Handler centrali (`start.py`, `buttons.py`).
  - `permissions/`: Controllo accessi dei topic Telegram.
  - `reports/`: Sistema di `report_user.py` asincrono.
  - `user_announcements_interactions/`: Handler specifici per il workflow degli annunci.
- `source/services/`: Servizi globali di messaggistica (`message_service.py`).

## 🤝 Contributi e Linee Guida (Pre-Push)
Se vuoi contribuire, assicurati di eseguire queste ispezioni prima del push:
1. **Security Checks**: Nessun `.env` hardcoded.
2. **Dead Code Elimination**: Elimina eventuali funzioni commentate o moduli importati ma non utilizzati.
3. **Architettura Asincrona**: Non inserire chiamate sincrone bloccanti all'interno dell'event loop di Pyrogram. Usa sempre `await` e astrazioni asincrone (es: `aiosqlite`).

## 📄 Licenza

Questo progetto è distribuito con licenza GNU Affero General Public License v3.0 (AGPL-3.0). Vedere il file `LICENSE` per dettagli.
