# 🌹 Comparazione con RoseBot - Pattern Analysis

**Data:** 18 Ottobre 2025  
**Scopo:** Analizzare pattern architetturali di bot Telegram professionali (RoseBot, MissRose) per applicarli a mipiaceunBOT

---

## 📚 Overview Bot Telegram Professionali

### **RoseBot Characteristics**
- **Linguaggio**: Python 3.x con Pyrogram/PTB
- **Architettura**: Modulare con plugin system
- **Database**: PostgreSQL per persistenza
- **Deployment**: Docker con auto-scaling
- **Monitoring**: Prometheus + Grafana
- **Testing**: Extensive unit/integration tests

### **Principali Pattern Identificati**

---

## 🏗️ 1. **Architettura Modulare Plugin-Based**

### **RoseBot Pattern**
```
rose/
├── modules/          # Ogni feature = 1 modulo
│   ├── admin.py
│   ├── bans.py
│   ├── warns.py
│   └── welcome.py
├── handlers/         # Handler separati da logica
├── database/         # ORM layer (SQLAlchemy)
└── utils/           # Utilities condivise
```

### **mipiaceunBOT Current**
```
source/
└── modules/
    ├── core/        # Mescolato start + buttons
    ├── permissions/
    ├── reports/
    └── user_announcements_interactions/  # Nome troppo lungo
```

### **✅ Miglioramento Proposto**
```
source/
├── plugins/          # Ogni feature = plugin autonomo
│   ├── announcements/
│   │   ├── __init__.py
│   │   ├── handlers.py
│   │   ├── service.py
│   │   └── models.py
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── handlers.py
│   │   └── service.py
│   └── permissions/
├── core/            # Core bot framework
└── database/        # Data layer
```

**Benefici**:
- ✅ Ogni plugin può essere disabilitato/abilitato via config
- ✅ Testing isolato per plugin
- ✅ Facile aggiungere nuove feature senza toccare core

---

## 🎯 2. **Handler Registration Pattern**

### **RoseBot Pattern**
```python
# Auto-discovery handlers con decoratori
from rose.core import bot, CommandHandler

@bot.command("start")
@bot.require_private
async def start_command(client, message):
    await message.reply("Welcome!")

# Plugin loader
def load_plugins():
    for module in discover_modules("plugins/"):
        importlib.import_module(module)
        # Decorators auto-register handlers
```

### **mipiaceunBOT Current**
```python
# main.py - Import manuale
from modules.core.start import start_handler
from modules.core.buttons import buttons_callback_handler
# ... devi ricordare di importare ogni handler
```

### **✅ Miglioramento Proposto**
```python
# core/decorators.py
def command(name: str, **kwargs):
    def decorator(func):
        # Auto-register nel bot instance
        get_bot().add_handler(CommandHandler(func, name))
        return func
    return decorator

# plugins/announcements/handlers.py
from core.decorators import command, callback

@command("start")
@require_group_member
async def start_handler(client, message):
    ...

@callback("new_event")
async def new_event_callback(client, query):
    ...

# main.py - Auto-discovery
from core.plugin_loader import load_all_plugins
load_all_plugins()  # Automatically finds and registers all handlers
```

**Benefici**:
- ✅ No import manuali in main.py
- ✅ Plugin self-contained
- ✅ Decoratori espressivi e leggibili

---

## 💾 3. **Database Layer (ORM Pattern)**

### **RoseBot Pattern**
```python
# Database models con SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    reported_user_id = Column(Integer, nullable=False)
    reporter_user_id = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Service layer
class ReportService:
    async def add_report(self, reported_id, reporter_id, reason):
        async with get_session() as session:
            report = Report(
                reported_user_id=reported_id,
                reporter_user_id=reporter_id,
                reason=reason
            )
            session.add(report)
            await session.commit()
```

### **mipiaceunBOT Current**
```python
# reports.json - Lettura/scrittura manuale
def load_reports():
    with open(REPORTS_FILE, 'r') as f:
        return json.load(f)

def save_reports(reports):
    with open(REPORTS_FILE, 'w') as f:
        json.dump(reports, f)
```

### **✅ Miglioramento Proposto**
```python
# database/models.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    reported_username = Column(String, index=True)
    reporter_username = Column(String)
    reason = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

# database/repository.py
class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add(self, report: Report) -> Report:
        self.session.add(report)
        await self.session.commit()
        return report
    
    async def get_count_for_user(self, username: str) -> int:
        result = await self.session.execute(
            select(func.count()).where(Report.reported_username == username)
        )
        return result.scalar()

# plugins/reports/service.py
class ReportService:
    def __init__(self, repository: ReportRepository):
        self.repo = repository
    
    async def report_user(self, reported: str, reporter: str, reason: str):
        report = Report(
            reported_username=reported,
            reporter_username=reporter,
            reason=reason
        )
        await self.repo.add(report)
        
        # Check ban threshold
        count = await self.repo.get_count_for_user(reported)
        if count >= 5:
            await self.ban_user(reported)
```

**Benefici**:
- ✅ Queries ottimizzate e type-safe
- ✅ Migrations automatiche (Alembic)
- ✅ Transazioni ACID
- ✅ Facile backup/restore

---

## 🔐 4. **Permission System**

### **RoseBot Pattern**
```python
# Middleware-based permissions
from rose.middleware import PermissionMiddleware

class GroupMemberMiddleware(PermissionMiddleware):
    async def check(self, client, message):
        return await is_group_member(message.from_user.id)
    
    def get_error_message(self):
        return "You must be a group member to use this command"

# Usage with decorator
@command("announce")
@require_permission(GroupMemberMiddleware)
async def announce_handler(client, message):
    # Only group members reach here
    pass
```

### **mipiaceunBOT Current**
```python
# Check manuale in ogni handler
async def buttons_callback_handler(client, callback_query):
    user = callback_query.from_user
    if not await is_user_allowed_by_username(client, user):
        await client.send_message(user.id, "❌ Solo utenti presenti...")
        return
    # ... rest of logic
```

### **✅ Miglioramento Proposto**
```python
# middleware/permissions.py
from functools import wraps
from core.exceptions import PermissionDenied

def require_group_member(func):
    @wraps(func)
    async def wrapper(client, update):
        user = getattr(update, 'from_user', None)
        if not user:
            return
        
        if not await check_membership(client, user.id):
            raise PermissionDenied("You must be a group member")
        
        return await func(client, update)
    return wrapper

# Global error handler
@bot.on_error()
async def error_handler(client, update, exception):
    if isinstance(exception, PermissionDenied):
        await update.reply(str(exception))
        return
    
    # Log other errors
    logger.exception("Unhandled error", exc_info=exception)

# Usage
@command("start")
@require_group_member
async def start_handler(client, message):
    # Clean handler logic, no permission checks
    pass
```

**Benefici**:
- ✅ DRY: no ripetizione check
- ✅ Centralizzato error handling
- ✅ Facile aggiungere nuovi permission checks

---

## 📊 5. **Logging e Monitoring**

### **RoseBot Pattern**
```python
# Structured logging con context
import structlog

logger = structlog.get_logger()

logger.info(
    "announcement_published",
    user_id=user.id,
    category="event",
    announcement_id=msg.id
)

# Metrics collection
from prometheus_client import Counter, Histogram

announcements_total = Counter(
    'bot_announcements_total',
    'Total announcements published',
    ['category']
)

@command("announce")
async def announce_handler(client, message):
    # ... logic
    announcements_total.labels(category='event').inc()
```

### **mipiaceunBOT Current**
```python
# Logging non strutturato
logging.info(f"{GREEN}[NUOVO ANNUNCIO] @{username} ha iniziato...{RESET}")
```

### **✅ Miglioramento Proposto**
```python
# utils/logging_config.py
import structlog

def setup_logging():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

# Usage
logger = structlog.get_logger()

logger.info(
    "announcement_started",
    user_id=user.id,
    username=user.username,
    category=category,
    action="start_compilation"
)

# Metrics (optional)
from datadog import statsd

statsd.increment('bot.announcement.started', tags=[f'category:{category}'])
```

**Benefici**:
- ✅ Logs machine-readable (JSON)
- ✅ Facile filtrare/aggregare
- ✅ Integrazione con log aggregators (ELK, Datadog)

---

## 🔄 6. **State Management**

### **RoseBot Pattern**
```python
# Redis-based state storage
from redis import asyncio as aioredis

class StateManager:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
    
    async def set_state(self, user_id: int, state: dict):
        await self.redis.setex(
            f"user:{user_id}:state",
            timedelta(hours=1),
            json.dumps(state)
        )
    
    async def get_state(self, user_id: int) -> dict:
        data = await self.redis.get(f"user:{user_id}:state")
        return json.loads(data) if data else {}
```

### **mipiaceunBOT Current**
```python
# In-memory dict
user_data = {}  # Perso al restart
```

### **✅ Miglioramento Proposto**

**Opzione 1: Redis (Production)**
```python
# core/state_manager.py
import aioredis
from typing import Optional

class RedisStateManager:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
    
    async def save_session(self, user_id: int, session: UserSession):
        await self.redis.setex(
            f"session:{user_id}",
            timedelta(minutes=30),
            session.json()
        )
    
    async def load_session(self, user_id: int) -> Optional[UserSession]:
        data = await self.redis.get(f"session:{user_id}")
        return UserSession.parse_raw(data) if data else None
```

**Opzione 2: File-based (Development)**
```python
# core/state_manager.py
from pathlib import Path
from filelock import FileLock

class FileStateManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
    
    async def save_session(self, user_id: int, session: UserSession):
        path = self.data_dir / f"session_{user_id}.json"
        lock_path = path.with_suffix('.lock')
        
        with FileLock(lock_path):
            with open(path, 'w') as f:
                f.write(session.json())
    
    async def load_session(self, user_id: int) -> Optional[UserSession]:
        path = self.data_dir / f"session_{user_id}.json"
        if not path.exists():
            return None
        
        with open(path) as f:
            return UserSession.parse_raw(f.read())
```

**Benefici**:
- ✅ Persistenza tra restart
- ✅ Scalabile su multiple instances (con Redis)
- ✅ TTL automatico per cleanup

---

## 🧪 7. **Testing Strategy**

### **RoseBot Pattern**
```python
# tests/test_announcements.py
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.send_message.return_value.id = 123
    return client

@pytest.mark.asyncio
async def test_announcement_publication(mock_client):
    service = AnnouncementService(mock_client)
    
    announcement = Announcement(
        category="event",
        title="Test Event",
        location="Test Location"
    )
    
    msg_id = await service.publish(announcement)
    
    assert msg_id == 123
    mock_client.send_message.assert_called_once()
```

### **mipiaceunBOT Current**
```python
# No tests ❌
```

### **✅ Miglioramento Proposto**
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_client():
    """Mock Pyrogram client"""
    client = AsyncMock()
    client.send_message = AsyncMock(return_value=MagicMock(id=123))
    client.delete_messages = AsyncMock()
    return client

@pytest.fixture
def session_manager():
    """Session manager with in-memory storage"""
    from core.session_manager import SessionManager
    return SessionManager()

# tests/plugins/test_announcements.py
@pytest.mark.asyncio
async def test_full_announcement_flow(mock_client, session_manager):
    """Test end-to-end announcement creation"""
    user_id = 12345
    
    # Start session
    session = session_manager.create_session(user_id, "event")
    
    # Simulate answering questions
    await collect_data_handler(mock_client, mock_message("Test Event"))
    await collect_data_handler(mock_client, mock_message("Test Location"))
    # ...
    
    # Verify session state
    session = session_manager.get_session(user_id)
    assert len(session.answers) == 6
    assert session.answers["🎫 Nome evento:"] == "Test Event"
    
    # Publish
    msg_id = await publish_announcement(mock_client, user_id)
    assert msg_id == 123
    
    # Verify cleanup
    assert session_manager.get_session(user_id) is None

# Run tests
# pytest tests/ --cov=source --cov-report=html
```

**Benefici**:
- ✅ Confidence in refactoring
- ✅ Regression prevention
- ✅ Documentation tramite tests

---

## 🚀 8. **Deployment e DevOps**

### **RoseBot Pattern**
```yaml
# docker-compose.yml
version: '3.8'
services:
  bot:
    build: .
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgres://user:pass@postgres/rosebot
      REDIS_URL: redis://redis:6379
    restart: unless-stopped
  
  postgres:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
```

### **mipiaceunBOT Current**
```bash
# Run manuale
python source/main.py
```

### **✅ Miglioramento Proposto**
```yaml
# docker-compose.yml
version: '3.8'
services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    volumes:
      - ./data:/app/data          # Persistent data
      - ./logs:/app/logs          # Logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

# GitHub Actions CI/CD
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## 📋 Checklist Completa RoseBot-Style

### **Architettura**
- [ ] Plugin system modulare
- [ ] Dependency injection
- [ ] Service layer pattern
- [ ] Repository pattern per data access
- [ ] Middleware per cross-cutting concerns

### **Code Quality**
- [ ] Type hints su tutte le funzioni
- [ ] Docstrings Google-style
- [ ] Linting (ruff, black, mypy)
- [ ] Pre-commit hooks
- [ ] Code coverage >70%

### **Database**
- [ ] SQLAlchemy ORM
- [ ] Alembic migrations
- [ ] Connection pooling
- [ ] Query optimization

### **Logging & Monitoring**
- [ ] Structured logging (JSON)
- [ ] Log levels per environment
- [ ] Metrics collection
- [ ] Error tracking (Sentry)

### **Testing**
- [ ] Unit tests per services
- [ ] Integration tests per flows
- [ ] Mocking Telegram API
- [ ] CI/CD pipeline

### **Deployment**
- [ ] Dockerization
- [ ] Environment-based config
- [ ] Health checks
- [ ] Graceful shutdown
- [ ] Backup strategy

### **Security**
- [ ] Rate limiting
- [ ] Input sanitization
- [ ] Secrets management (env vars)
- [ ] Audit logging

### **Documentation**
- [ ] Architecture diagrams
- [ ] API documentation
- [ ] Setup instructions
- [ ] Contributing guidelines

---

## 🎯 Priority Implementation Order

### **Phase 1: Foundation** (Week 1)
1. Session Manager (elimina state globale)
2. Message Service (fix deletion issues)
3. Plugin structure (modularità)

### **Phase 2: Quality** (Week 2)
4. Validation service
5. Logging strutturato
6. Basic tests

### **Phase 3: Scale** (Week 3)
7. Database migration (JSON → SQLite)
8. Middleware permissions
9. Docker deployment

### **Phase 4: Polish** (Week 4)
10. Complete test coverage
11. Documentation
12. CI/CD setup

---

## 💡 Lessons from RoseBot

### **Do's ✅**
- Keep handlers thin (delegate to services)
- Use type hints everywhere
- Test business logic separately from Telegram API
- Document architecture decisions
- Use dependency injection

### **Don'ts ❌**
- Don't put business logic in handlers
- Don't use global state
- Don't hardcode configuration
- Don't skip error handling
- Don't ignore logging

---

## 📚 Resources

- **RoseBot GitHub**: (closed source but patterns visible from forks)
- **Pyrogram Docs**: https://docs.pyrogram.org
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Structlog**: https://www.structlog.org
- **Python Best Practices**: https://docs.python-guide.org

---

**Conclusione**: Applicando questi pattern, mipiaceunBOT diventerà un bot di livello enterprise, manutenibile e scalabile come RoseBot! 🚀
