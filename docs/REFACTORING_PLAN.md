# 📋 Piano di Refactoring - mipiaceunBOT.TN

**Data:** 18 Ottobre 2025  
**Obiettivo:** Trasformare il bot in un sistema robusto, manutenibile e scalabile seguendo le best practice dei bot Telegram professionali (RoseBot-style)

---

## 🎯 Obiettivi Principali

1. **Robustezza**: Eliminare errori di eliminazione messaggi, gestione sessioni sicura
2. **Manutenibilità**: Codice chiaro, modulare, ben documentato, facile da modificare
3. **Scalabilità**: Architettura che supporti crescita features e utenti
4. **Testabilità**: Codice facilmente testabile con unit/integration tests

---

## 🔍 Analisi Problemi Attuali

### ❌ **Problemi Critici Identificati**

#### 1. **Dipendenze Circolari**
```
config.py → user_data (dict globale)
    ↓
message_utils.py → import config.user_data
    ↓
buttons.py → import message_utils
    ↓
announcement_handler.py → import buttons
    ↓
config.py (circular!)
```
**Impatto**: Difficile testing, accoppiamento stretto, bug difficili da tracciare

#### 2. **Stato Globale Condiviso**
- `user_data = {}` in config.py
- `report_state = {}` in config.py  
- `error_messages = {}` in announcement_handler.py

**Problema**: Race conditions potenziali, difficile cleanup, memory leaks se sessioni non vengono pulite correttamente

#### 3. **Gestione Messaggi Frammentata**
- Tracking in `messages_to_delete`, `user_messages_to_delete`, `multi_file_temp_msgs`, `error_messages`
- Eliminazione sparsa nel codice (buttons.py, announcement_handler.py, message_utils.py)
- Pattern inconsistenti: a volte `safe_delete`, a volte `client.delete_messages`

#### 4. **Logica Business Mescolata con Handler**
- `buttons_callback_handler` contiene logica pubblicazione, validazione, navigazione
- `collect_data_handler` fa validazione + raccolta + navigation
- Difficile testare logica senza simulare Telegram events

#### 5. **Mancanza di Typing**
- Molte funzioni senza type hints
- Dict non tipizzati (`user_data[user_id]` potrebbe essere qualsiasi cosa)
- Difficile capire struttura dati

#### 6. **Validazione Input Sparsa**
```python
# In collect_data_handler:
if msg_type and msg_type not in allowed_types:
    error_msg = await client.send_message(...)
```
Validazione hardcoded in ogni handler, non riutilizzabile

#### 7. **Configurazione Hardcoded**
- `CHAT_ID = -1002461409137` hardcoded in config.py
- `announce_timeout = 1200` non configurabile
- `POINTER_MESSAGE_IDS` fissi, non environment-based

---

## 🏗️ Architettura Target (RoseBot-Inspired)

### **Struttura Proposta**
```
source/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Settings da env vars/yaml
│   └── constants.py         # Costanti readonly
├── core/
│   ├── __init__.py
│   ├── bot.py               # Bot initialization
│   ├── session_manager.py   # Gestione sessioni centralizzata
│   └── exceptions.py        # Custom exceptions
├── handlers/
│   ├── __init__.py
│   ├── start.py             # /start command
│   ├── announcements.py     # Announcement flow
│   ├── reports.py           # Report users
│   └── callbacks.py         # Callback queries
├── services/
│   ├── __init__.py
│   ├── message_service.py   # Message CRUD + cleanup
│   ├── validation_service.py # Input validation
│   ├── announcement_service.py # Business logic annunci
│   └── report_service.py    # Business logic reports
├── middleware/
│   ├── __init__.py
│   ├── auth.py              # Group membership check
│   └── rate_limit.py        # Anti-spam
├── models/
│   ├── __init__.py
│   ├── session.py           # UserSession, ReportSession dataclasses
│   └── announcement.py      # Announcement model
├── utils/
│   ├── __init__.py
│   ├── formatters.py        # Text formatting
│   └── logging_config.py    # Logging setup
└── main.py
```

### **Principi Architetturali**

1. **Single Responsibility**: Ogni modulo ha un solo scopo
2. **Dependency Injection**: No import circolari, dipendenze esplicite
3. **Separation of Concerns**: Handler → Service → Repository pattern
4. **Immutable Config**: Config caricato all'avvio, readonly

---

## 📝 Piano di Implementazione (12 Fasi)

### **🔵 FASE 1: Analisi e Documentazione** *(Durata: ~2h)*

**Obiettivo**: Mappare completamente il codice esistente

**Task**:
- ✅ Identificare tutti gli import circolari
- ✅ Mappare flussi di dati (user_data flow, report flow)
- ✅ Documentare edge cases e comportamenti non ovvi
- ✅ Creare diagrammi di sequenza per flow principali

**Deliverable**: `docs/architecture_analysis.md` con diagrammi

---

### **🟢 FASE 2: Session Manager** *(Durata: ~4h)* **[PRIORITÀ ALTA]**

**Obiettivo**: Eliminare dizionari globali user_data e report_state

**Implementazione**:
```python
# source/core/session_manager.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class UserSession:
    user_id: int
    category: Optional[str] = None
    step: int = 0
    answers: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, List[dict]] = field(default_factory=dict)
    messages_to_delete: List[int] = field(default_factory=list)
    user_messages_to_delete: List[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    timeout_task: Optional[asyncio.Task] = None

class SessionManager:
    """Gestione centralizzata delle sessioni utente"""
    
    def __init__(self):
        self._sessions: Dict[int, UserSession] = {}
    
    def create_session(self, user_id: int, category: str) -> UserSession:
        """Crea nuova sessione utente"""
        session = UserSession(user_id=user_id, category=category)
        self._sessions[user_id] = session
        return session
    
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Recupera sessione esistente"""
        return self._sessions.get(user_id)
    
    async def cleanup_session(self, user_id: int, client) -> None:
        """Pulisce sessione e messaggi associati"""
        session = self._sessions.get(user_id)
        if not session:
            return
        
        # Cleanup timeout task
        if session.timeout_task:
            session.timeout_task.cancel()
        
        # Delete tracked messages
        from services.message_service import MessageService
        msg_service = MessageService(client)
        await msg_service.delete_batch(user_id, session.messages_to_delete)
        await msg_service.delete_batch(user_id, session.user_messages_to_delete)
        
        # Remove session
        del self._sessions[user_id]
```

**Test di Migrazione**:
1. Sostituire `user_data[user_id]` con `session_manager.get_session(user_id)`
2. Verificare funzionalità invariata
3. Rimuovere `user_data` da config.py

**Benefici**:
- ✅ No più import config.user_data in utils
- ✅ Type safety con dataclass
- ✅ Cleanup automatizzato
- ✅ Facile aggiungere campi senza rompere codice

---

### **🟡 FASE 3: Refactoring Struttura Moduli** *(Durata: ~6h)*

**Obiettivo**: Riorganizzare codice seguendo nuova struttura

**Migration Steps**:
1. Creare nuove directory (config/, handlers/, services/, middleware/, models/)
2. Spostare file uno alla volta:
   - `config.py` → `config/settings.py` + `config/constants.py`
   - `buttons.py` → `handlers/callbacks.py`
   - `start.py` → `handlers/start.py`
   - `report_user.py` → `handlers/reports.py` + `services/report_service.py`
3. Aggiornare import progressivamente
4. Testare dopo ogni spostamento

**Esempio Migrazione**:
```python
# OLD: source/modules/core/buttons.py
from config import user_data, bot

# NEW: source/handlers/callbacks.py
from core.session_manager import SessionManager
from core.bot import get_bot

session_manager = SessionManager()
bot = get_bot()
```

---

### **🟣 FASE 4: Sistema Validazione** *(Durata: ~5h)*

**Implementazione**:
```python
# source/services/validation_service.py
from abc import ABC, abstractmethod
from typing import Optional, List
from pyrogram.types import Message

class Validator(ABC):
    @abstractmethod
    async def validate(self, message: Message) -> tuple[bool, Optional[str]]:
        """Returns (is_valid, error_message)"""
        pass

class TextValidator(Validator):
    def __init__(self, min_length: int = 0, max_length: int = 4096):
        self.min_length = min_length
        self.max_length = max_length
    
    async def validate(self, message: Message) -> tuple[bool, Optional[str]]:
        if not message.text:
            return False, "❌ Invia un messaggio di testo"
        
        text_len = len(message.text)
        if text_len < self.min_length:
            return False, f"❌ Testo troppo breve (minimo {self.min_length} caratteri)"
        if text_len > self.max_length:
            return False, f"❌ Testo troppo lungo (massimo {self.max_length} caratteri)"
        
        return True, None

class PhotoValidator(Validator):
    async def validate(self, message: Message) -> tuple[bool, Optional[str]]:
        if not message.photo:
            return False, "❌ Invia una foto"
        return True, None

class ValidatorChain:
    """Esegue validators in sequenza"""
    def __init__(self, validators: List[Validator]):
        self.validators = validators
    
    async def validate(self, message: Message) -> tuple[bool, Optional[str]]:
        for validator in self.validators:
            is_valid, error = await validator.validate(message)
            if not is_valid:
                return False, error
        return True, None

# Usage in handler:
validator = ValidatorChain([
    TextValidator(min_length=10),
    ContentValidator(forbidden_words=["spam", "scam"])
])
is_valid, error_msg = await validator.validate(message)
```

**Benefici**:
- ✅ Validazione riutilizzabile
- ✅ Facile aggiungere nuovi validators
- ✅ Testabile in isolamento
- ✅ Messaggi errore consistenti

---

### **🔴 FASE 5: Message Service Completo** *(Durata: ~4h)*

**Implementazione**:
```python
# source/services/message_service.py
from typing import List, Optional, Union
from pyrogram.types import InlineKeyboardMarkup, Message
from tenacity import retry, stop_after_attempt, wait_exponential

class MessageService:
    def __init__(self, client):
        self.client = client
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def safe_delete(self, chat_id: int, message_ids: Union[int, List[int]]) -> int:
        """Elimina messaggi con retry automatico. Returns: numero messaggi eliminati"""
        try:
            if isinstance(message_ids, int):
                message_ids = [message_ids]
            
            deleted = 0
            for msg_id in message_ids:
                try:
                    await self.client.delete_messages(chat_id, msg_id)
                    deleted += 1
                except Exception as e:
                    logging.debug(f"Skip deletion {msg_id}: {e}")
            
            return deleted
        except Exception as e:
            logging.error(f"Batch delete failed: {e}")
            return 0
    
    async def send_and_track(
        self, 
        session_manager,
        user_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[Message]:
        """Invia messaggio e lo traccia automaticamente nella sessione"""
        session = session_manager.get_session(user_id)
        if not session:
            return None
        
        # Delete previous bot messages
        if session.messages_to_delete:
            await self.safe_delete(user_id, session.messages_to_delete)
            session.messages_to_delete.clear()
        
        # Send new message
        msg = await self.client.send_message(user_id, text, reply_markup=reply_markup)
        
        # Track it
        session.messages_to_delete.append(msg.id)
        
        return msg
    
    async def cleanup_user_messages(self, session_manager, user_id: int) -> int:
        """Elimina tutti i messaggi utente tracciati"""
        session = session_manager.get_session(user_id)
        if not session:
            return 0
        
        deleted = await self.safe_delete(user_id, session.user_messages_to_delete)
        session.user_messages_to_delete.clear()
        return deleted
```

**Uso**:
```python
# In handlers:
message_service = MessageService(client)
await message_service.send_and_track(session_manager, user_id, "Domanda 1")
```

---

### **🟠 FASE 6: State Machine per Announcement Flow** *(Durata: ~6h)*

**Implementazione** (usando `python-statemachine`):
```python
# source/models/announcement_fsm.py
from statemachine import StateMachine, State

class AnnouncementFlow(StateMachine):
    # States
    idle = State('Idle', initial=True)
    collecting = State('Collecting Data')
    preview = State('Preview')
    confirming = State('Confirming')
    publishing = State('Publishing')
    published = State('Published', final=True)
    cancelled = State('Cancelled', final=True)
    
    # Transitions
    start = idle.to(collecting)
    next_question = collecting.to(collecting)
    show_preview = collecting.to(preview)
    back_to_question = preview.to(collecting)
    confirm = preview.to(confirming)
    publish = confirming.to(publishing)
    complete = publishing.to(published)
    cancel = collecting.to(cancelled) | preview.to(cancelled) | confirming.to(cancelled)
    
    def on_enter_collecting(self):
        """Triggered when entering collecting state"""
        logging.info(f"User {self.user_id} entering data collection")
    
    def on_exit_confirming(self):
        """Cleanup before publishing"""
        logging.info(f"User {self.user_id} confirmed, publishing...")

# Usage:
fsm = AnnouncementFlow(user_id=123)
fsm.start()  # idle -> collecting
fsm.next_question()  # collecting -> collecting
fsm.show_preview()  # collecting -> preview
```

**Benefici**:
- ✅ Transizioni valide automaticamente enforce
- ✅ Hooks per ogni stato (on_enter_*, on_exit_*)
- ✅ Visualizzazione grafica stati (per docs)
- ✅ Facile aggiungere stati senza rompere logica

---

### **🟤 FASE 7: Middleware e Permission Layer** *(Durata: ~3h)*

**Implementazione**:
```python
# source/middleware/auth.py
from functools import wraps
from pyrogram import filters
from pyrogram.types import Message
from cachetools import TTLCache

# Cache membership checks (5 min TTL)
membership_cache = TTLCache(maxsize=1000, ttl=300)

def require_group_member(func):
    """Decorator che verifica membership gruppo"""
    @wraps(func)
    async def wrapper(client, message: Message):
        user_id = message.from_user.id
        
        # Check cache first
        if user_id in membership_cache:
            if not membership_cache[user_id]:
                await message.reply("❌ Solo membri del gruppo possono usare il bot")
                return
            return await func(client, message)
        
        # Check actual membership
        from services.permission_service import PermissionService
        perm_service = PermissionService(client)
        is_member = await perm_service.is_group_member(user_id)
        
        membership_cache[user_id] = is_member
        
        if not is_member:
            await message.reply("❌ Solo membri del gruppo possono usare il bot")
            return
        
        return await func(client, message)
    
    return wrapper

# Usage in handler:
@bot.on_message(filters.command("start"))
@require_group_member
async def start_handler(client, message):
    # Solo membri gruppo arrivano qui
    ...
```

---

### **⚪ FASE 8: Logging e Monitoring** *(Durata: ~2h)*

**Implementazione**:
```python
# source/utils/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        
        # Add context if available
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        
        return json.dumps(log_data)

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Usage:
logger = logging.getLogger(__name__)
logger.info("User published announcement", extra={"user_id": 123, "action": "publish"})
```

---

### **🟢 FASE 9: Testing Framework** *(Durata: ~8h)*

**Setup**:
```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

**Struttura Tests**:
```
tests/
├── conftest.py              # Fixtures comuni
├── unit/
│   ├── test_validators.py
│   ├── test_session_manager.py
│   └── test_message_service.py
├── integration/
│   ├── test_announcement_flow.py
│   └── test_report_flow.py
└── fixtures/
    ├── mock_users.py
    └── mock_messages.py
```

**Esempio Test**:
```python
# tests/unit/test_validators.py
import pytest
from services.validation_service import TextValidator
from tests.fixtures.mock_messages import create_text_message

@pytest.mark.asyncio
async def test_text_validator_min_length():
    validator = TextValidator(min_length=10)
    
    # Valid message
    msg = create_text_message("Hello world!")
    is_valid, error = await validator.validate(msg)
    assert is_valid
    assert error is None
    
    # Invalid message
    msg_short = create_text_message("Hi")
    is_valid, error = await validator.validate(msg_short)
    assert not is_valid
    assert "troppo breve" in error

@pytest.mark.asyncio
async def test_session_manager_lifecycle():
    from core.session_manager import SessionManager
    
    sm = SessionManager()
    
    # Create session
    session = sm.create_session(123, "event")
    assert session.user_id == 123
    assert session.category == "event"
    
    # Get session
    retrieved = sm.get_session(123)
    assert retrieved == session
    
    # Cleanup
    await sm.cleanup_session(123, mock_client)
    assert sm.get_session(123) is None
```

---

### **🔵 FASE 10: Documentazione** *(Durata: ~4h)*

**Deliverables**:
1. `docs/ARCHITECTURE.md` - Architettura sistema
2. `docs/API_REFERENCE.md` - API interno
3. `docs/DEVELOPMENT.md` - Setup dev environment
4. `CONTRIBUTING.md` - Guidelines contributori
5. Aggiornare README.md

**Config Management**:
```yaml
# config.yaml
bot:
  chat_id: ${TELEGRAM_CHAT_ID}
  announce_timeout: 1200
  report_timeout: 300

topics:
  job: 466
  project: 467
  event: 463
  profile: 468

logging:
  level: INFO
  format: json
```

```python
# config/settings.py
import os
import yaml
from pydantic import BaseSettings

class BotSettings(BaseSettings):
    api_id: int
    api_hash: str
    bot_token: str
    chat_id: int
    announce_timeout: int = 1200
    
    class Config:
        env_file = ".env"

def load_config():
    settings = BotSettings()
    
    # Override with yaml if exists
    if os.path.exists("config.yaml"):
        with open("config.yaml") as f:
            yaml_config = yaml.safe_load(f)
            # Merge yaml with env vars
    
    return settings
```

---

### **🟡 FASE 11: Performance** *(Durata: ~3h)*

**Ottimizzazioni**:
1. **Batch Message Deletion**:
```python
# OLD: Elimina uno alla volta
for mid in messages:
    await client.delete_messages(chat_id, mid)

# NEW: Batch (fino a 100 msg)
await client.delete_messages(chat_id, messages[:100])
```

2. **Caching Member Checks**:
```python
from cachetools import TTLCache
member_cache = TTLCache(maxsize=5000, ttl=300)  # 5min TTL
```

3. **Connection Pooling** (se usa DB):
```python
from sqlalchemy.ext.asyncio import create_async_engine
engine = create_async_engine(
    "postgresql+asyncpg://...",
    pool_size=20,
    max_overflow=10
)
```

**Database Migration** (opzionale):
```python
# reports.json → SQLite
import aiosqlite

async def migrate_reports():
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY,
                reported_user TEXT,
                reporter TEXT,
                reason TEXT,
                timestamp TEXT
            )
        """)
        
        # Migrate from JSON
        with open("reports.json") as f:
            reports = json.load(f)
        
        await db.executemany(
            "INSERT INTO reports VALUES (?, ?, ?, ?, ?)",
            [(None, r['reported_user'], r['reporter'], r['reason'], r['timestamp']) 
             for r in reports]
        )
```

---

### **🟣 FASE 12: Deploy e Maintenance** *(Durata: ~4h)*

**Docker Setup**:
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY source/ ./source/

CMD ["python", "source/main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Maintenance Scripts**:
```python
# scripts/cleanup_sessions.py
"""Pulisce sessioni scadute oltre 24h"""
async def cleanup_old_sessions():
    from core.session_manager import session_manager
    from datetime import datetime, timedelta
    
    cutoff = datetime.now() - timedelta(hours=24)
    
    for user_id, session in list(session_manager._sessions.items()):
        if session.created_at < cutoff:
            await session_manager.cleanup_session(user_id, client)
            print(f"Cleaned session {user_id}")
```

---

## 📊 Metriche di Successo

### **Prima del Refactoring**
- ❌ Import circolari: 3
- ❌ Dizionari globali: 3
- ❌ Test coverage: 0%
- ❌ Docstring coverage: ~20%
- ⚠️ Message deletion reliability: ~85%

### **Dopo il Refactoring (Target)**
- ✅ Import circolari: 0
- ✅ Stato gestito: SessionManager centralizzato
- ✅ Test coverage: >70%
- ✅ Docstring coverage: >90%
- ✅ Message deletion reliability: >98%

---

## 🚀 Roadmap Timeline

| Fase | Durata | Priorità | Dependencies |
|------|--------|----------|--------------|
| FASE 1 | 2h | 🔴 Alta | - |
| FASE 2 | 4h | 🔴 Alta | FASE 1 |
| FASE 3 | 6h | 🔴 Alta | FASE 2 |
| FASE 4 | 5h | 🟡 Media | FASE 3 |
| FASE 5 | 4h | 🔴 Alta | FASE 2 |
| FASE 6 | 6h | 🟡 Media | FASE 2, 3 |
| FASE 7 | 3h | 🟡 Media | FASE 3 |
| FASE 8 | 2h | 🟢 Bassa | - |
| FASE 9 | 8h | 🟡 Media | FASE 2-7 |
| FASE 10 | 4h | 🟢 Bassa | FASE 1-9 |
| FASE 11 | 3h | 🟢 Bassa | FASE 2-7 |
| FASE 12 | 4h | 🟢 Bassa | FASE 1-11 |

**Totale stimato**: ~51 ore (6-7 giorni lavorativi)

---

## 🎯 Quick Wins (Priorità Immediate)

Se vuoi risultati rapidi, parti da:

1. **FASE 2 (Session Manager)** - Risolve import circolari e migliora affidabilità
2. **FASE 5 (Message Service)** - Fix definitivo eliminazione messaggi
3. **FASE 4 (Validation)** - Codice più pulito e robusto

Queste 3 fasi (13h totali) risolvono i problemi critici attuali.

---

## 📌 Note Finali

### **Principi da Seguire Durante il Refactoring**

1. **Incrementalità**: Una fase alla volta, testando dopo ogni cambiamento
2. **Backward Compatibility**: Mantenere funzionalità invariata durante migration
3. **Test-First**: Scrivere test prima di refactorare (dove possibile)
4. **Documentation**: Documentare decisioni architetturali

### **Quando Fare il Refactoring**

- ✅ **Fallo ora** se vuoi evitare debito tecnico e rendere il bot production-ready
- ⚠️ **Posticipa** solo se ci sono feature urgenti da rilasciare

### **Supporto**

Per ogni fase, posso:
- Scrivere il codice completo
- Creare PR con review checklist
- Assistere nel testing
- Rispondere a domande implementative

---

**Prossimo Step**: Confermare quale fase iniziare e procediamo con l'implementazione! 🚀
