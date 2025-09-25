# README per versione webhook

## 🤖 Telegram Bot - Versione Webhook

Questa è la versione webhook del bot, ottimizzata per deploy gratuito su Render.com.

### 🏗️ Architettura

- **Web Server**: Flask (riceve POST da Telegram)
- **Storage**: Redis (sessioni utente e stato temporaneo)  
- **Persistenza**: JSON file con FileLock (segnalazioni)
- **Deploy**: Render.com (piano gratuito)

### 🚀 Deploy su Render

#### 1. Setup Redis Database
- Crea account gratuito su [Upstash](https://upstash.com/)
- Crea nuovo Redis database
- Copia la **REDIS_URL** (inizia con `rediss://`)

#### 2. Crea Web Service su Render
- Fork questo repo su GitHub 
- Connetti Render al repository
- Build command: `pip install -r requirements.txt`
- Start command: `python start.py`

#### 3. Environment Variables (Dashboard Render)


#### 4. Registra webhook manualmente
Dopo il deploy, esegui:
```bash
curl -X POST "https://api.telegram.org/bot8438427152:AAGHyETuC7vQ-8lbnDx9U4Zphz96R43tpTg/setWebhook" \
     -d "url=https://your-app-name.onrender.com/webhook"
```

### 🔧 Differenze da versione polling

| Aspetto | Polling (originale) | Webhook (questa) |
|---------|-------------------|------------------|
| **Processo** | `bot.run()` loop continuo | Flask server HTTP |
| **Stato** | `user_data = {}` memoria | Redis TTL database |
| **Timeout** | `asyncio.create_task()` | Redis expiration |
| **Costo** | $7/mese background worker | Gratis web service |
| **Scalabilità** | Singola istanza | Auto-scale Render |

### 📁 Struttura File

```
source_webh/
├── main.py              # Flask webhook server
├── config.py            # Config + Redis wrappers  
├── storage.py           # Redis abstraction layer
├── requirements.txt     # Dependencies
├── Dockerfile          # Container build
└── modules/
    ├── start.py         # /start handler
    ├── buttons.py       # Callback handlers
    ├── topic_guardian.py # Moderazione topic
    └── user_announcements_interactions/
        ├── collect_data.py        # Raccolta dati multi-step
        ├── announcement_compiler.py # Preview/publish
        └── report_user.py         # Segnalazioni + GDPR
```

### 🧪 Test Locale

```bash
# 1. Installa Redis locale
docker run -d -p 6379:6379 --name redis redis:alpine

# 2. Installa dipendenze  
pip install -r requirements.txt

# 3. Configura .env
cp ../bot_infos.env .
echo "REDIS_URL=redis://localhost:6379" >> bot_infos.env
echo "WEBHOOK_URL=https://your-ngrok.io/webhook" >> bot_infos.env

# 4. Avvia (con ngrok per tunnel pubblico)
python main.py
```

### 📊 Monitoring

- **Health check**: `GET /` (status bot e Redis)
- **Stats**: `GET /stats` (sessioni attive, Redis)
- **Logs**: Render dashboard o `heroku logs --tail`

### 🔄 Migrazione da polling

1. **Backup reports.json** dalla versione originale
2. **Copy** in `source_webh/reports.json`  
3. **Deploy** versione webhook
4. **Test** funzionalità principali
5. **Update** webhook URL nel BotFather

### ⚠️ Note Importanti

- **Redis TTL**: Sessioni scadono automaticamente (no task cleanup)
- **HTTP 200**: Webhook ritorna sempre 200 (evita retry loop)
- **FileLock**: reports.json usa ancora file locking (non Redis)
- **Cold start**: Prima richiesta può richiedere 2-5 secondi
- **Timeout**: Max 30 secondi per richiesta HTTP su Render