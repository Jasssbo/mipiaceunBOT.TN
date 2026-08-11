# 🎯 Quick Start Guide - Refactoring mipiaceunBOT

**Per chi ha fretta**: Questa guida ti dice esattamente cosa fare ADESSO per migliorare il bot.

---

## 🚨 Problemi Critici ATTUALI

### 1. **Import Circolari** ❌
```
config.py ← message_utils.py ← announcement_handler.py ← buttons.py ← config.py
```
**Impatto**: Difficile testare, bug nascosti

### 2. **Eliminazione Messaggi Inaffidabile** ⚠️
- Tracking sparso in 4 liste diverse
- Eliminazione non sempre funziona
- Messaggi utente rimangono in chat

### 3. **Stato Globale** 💥
- `user_data = {}` accessibile ovunque
- Memory leaks se sessioni non pulite
- Race conditions

---

## ✅ Soluzione: 3 Quick Wins (1 Giorno)

### **Quick Win #1: Session Manager** (3-4 ore)

**Crea**: `source/core/session_manager.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

@dataclass
class UserSession:
    """Sessione utente tipizzata"""
    user_id: int
    category: Optional[str] = None
    step: int = 0
    answers: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, List[dict]] = field(default_factory=dict)
    
    # Message tracking
    messages_to_delete: List[int] = field(default_factory=list)
    user_messages_to_delete: List[int] = field(default_factory=list)
    multi_file_temp_msgs: List[int] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    timeout_task: Optional[asyncio.Task] = None

class SessionManager:
    """
    Gestione centralizzata delle sessioni utente.
    Sostituisce il dizionario globale user_data.
    """
    
    def __init__(self):
        self._sessions: Dict[int, UserSession] = {}
    
    def create_session(self, user_id: int, category: str) -> UserSession:
        """Crea una nuova sessione"""
        session = UserSession(user_id=user_id, category=category)
        self._sessions[user_id] = session
        return session
    
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Recupera sessione esistente"""
        return self._sessions.get(user_id)
    
    def has_session(self, user_id: int) -> bool:
        """Controlla se esiste una sessione"""
        return user_id in self._sessions
    
    async def cleanup_session(self, user_id: int, message_service=None) -> None:
        """
        Pulisce sessione e tutti i messaggi associati.
        
        Args:
            user_id: ID utente
            message_service: MessageService per eliminare messaggi (opzionale)
        """
        session = self._sessions.get(user_id)
        if not session:
            return
        
        # Cancel timeout task
        if session.timeout_task:
            try:
                session.timeout_task.cancel()
            except Exception:
                pass
        
        # Delete messages if service provided
        if message_service:
            await message_service.delete_batch(
                user_id, 
                session.messages_to_delete + 
                session.user_messages_to_delete + 
                session.multi_file_temp_msgs
            )
        
        # Remove session
        del self._sessions[user_id]
    
    def get_all_sessions(self) -> List[UserSession]:
        """Ritorna tutte le sessioni attive"""
        return list(self._sessions.values())

# Singleton instance
_session_manager = SessionManager()

def get_session_manager() -> SessionManager:
    """Ritorna l'istanza singleton del SessionManager"""
    return _session_manager
```

**Migrazione**:
```python
# PRIMA (config.py)
user_data = {}
user_data[user_id] = {"category": "event", "step": 0}

# DOPO (qualsiasi file)
from core.session_manager import get_session_manager

session_manager = get_session_manager()
session = session_manager.create_session(user_id, "event")
```

**Vantaggi immediati**:
- ✅ No più import config.user_data
- ✅ Type safety
- ✅ Cleanup automatizzato

---

### **Quick Win #2: Message Service Robusto** (2-3 ore)

**Crea**: `source/services/message_service.py`

```python
import logging
from typing import List, Optional, Union
from pyrogram.types import InlineKeyboardMarkup, Message
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pyrogram import errors

logger = logging.getLogger(__name__)

class MessageService:
    """
    Servizio centralizzato per gestione messaggi.
    Gestisce invio, eliminazione e tracking automatico.
    """
    
    def __init__(self, client):
        self.client = client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((errors.FloodWait, errors.RPCError))
    )
    async def safe_delete(self, chat_id: int, message_ids: Union[int, List[int]]) -> int:
        """
        Elimina messaggi con retry automatico.
        
        Returns:
            Numero di messaggi eliminati con successo
        """
        if isinstance(message_ids, int):
            message_ids = [message_ids]
        
        if not message_ids:
            return 0
        
        deleted_count = 0
        for msg_id in message_ids:
            try:
                await self.client.delete_messages(chat_id, msg_id)
                deleted_count += 1
            except errors.MessageDeleteForbidden:
                logger.debug(f"Cannot delete message {msg_id} - forbidden")
            except Exception as e:
                logger.warning(f"Failed to delete message {msg_id}: {e}")
        
        return deleted_count
    
    async def delete_batch(self, chat_id: int, message_ids: List[int]) -> int:
        """
        Elimina messaggi in batch (fino a 100 per volta).
        Più efficiente di eliminazione singola.
        """
        if not message_ids:
            return 0
        
        # Pyrogram supporta batch delete fino a 100 msg
        deleted = 0
        for i in range(0, len(message_ids), 100):
            batch = message_ids[i:i+100]
            try:
                await self.client.delete_messages(chat_id, batch)
                deleted += len(batch)
            except Exception as e:
                logger.error(f"Batch delete failed: {e}")
                # Fallback to single deletion
                for msg_id in batch:
                    deleted += await self.safe_delete(chat_id, msg_id)
        
        return deleted
    
    async def send_and_track(
        self,
        session,
        chat_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[Message]:
        """
        Invia messaggio e lo traccia automaticamente nella sessione.
        Elimina i messaggi bot precedenti prima di inviare.
        
        Args:
            session: UserSession object
            chat_id: ID chat destinazione
            text: Testo messaggio
            reply_markup: Keyboard inline (opzionale)
        
        Returns:
            Message object o None se errore
        """
        # Delete previous bot messages
        if session.messages_to_delete:
            await self.delete_batch(chat_id, session.messages_to_delete)
            session.messages_to_delete.clear()
        
        # Send new message
        try:
            msg = await self.client.send_message(
                chat_id,
                text,
                reply_markup=reply_markup
            )
            
            # Track it
            session.messages_to_delete.append(msg.id)
            
            return msg
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None
    
    async def cleanup_user_messages(self, session) -> int:
        """
        Elimina tutti i messaggi utente tracciati nella sessione.
        
        Returns:
            Numero messaggi eliminati
        """
        deleted = await self.delete_batch(
            session.user_id,
            session.user_messages_to_delete
        )
        session.user_messages_to_delete.clear()
        return deleted
```

**Migrazione**:
```python
# PRIMA (announcement_handler.py)
from config import user_data
await client.delete_messages(user_id, msg_id)
msg = await client.send_message(user_id, "Test")
user_data[user_id]["messages_to_delete"].append(msg.id)

# DOPO
from services.message_service import MessageService

msg_service = MessageService(client)
msg = await msg_service.send_and_track(session, user_id, "Test")
# Tracking automatico, cleanup automatico!
```

**Vantaggi immediati**:
- ✅ Eliminazione affidabile con retry
- ✅ Batch operations (performance)
- ✅ Tracking automatico
- ✅ Codice più pulito

---

### **Quick Win #3: Validation Service** (2 ore)

**Crea**: `source/services/validation_service.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from pyrogram.types import Message

class Validator(ABC):
    """Base validator interface"""
    
    @abstractmethod
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        """
        Valida un messaggio.
        
        Returns:
            (is_valid, error_message)
        """
        pass

class TextValidator(Validator):
    """Valida messaggi di testo"""
    
    def __init__(self, min_length: int = 0, max_length: int = 4096):
        self.min_length = min_length
        self.max_length = max_length
    
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        if not message.text:
            return False, "❌ Invia un messaggio di testo"
        
        text_len = len(message.text.strip())
        
        if text_len < self.min_length:
            return False, f"❌ Testo troppo breve (minimo {self.min_length} caratteri)"
        
        if text_len > self.max_length:
            return False, f"❌ Testo troppo lungo (massimo {self.max_length} caratteri)"
        
        return True, None

class PhotoValidator(Validator):
    """Valida messaggi con foto"""
    
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        if not message.photo:
            return False, "❌ Invia una foto"
        return True, None

class DocumentValidator(Validator):
    """Valida messaggi con documenti"""
    
    def __init__(self, max_size_mb: Optional[int] = None):
        self.max_size_bytes = max_size_mb * 1024 * 1024 if max_size_mb else None
    
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        if not message.document:
            return False, "❌ Invia un documento"
        
        if self.max_size_bytes and message.document.file_size > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            return False, f"❌ File troppo grande (massimo {max_mb}MB)"
        
        return True, None

class TypeValidator(Validator):
    """Valida il tipo di messaggio"""
    
    def __init__(self, allowed_types: List[str]):
        """
        Args:
            allowed_types: Lista di tipi consentiti (es. ["text", "photo", "document"])
        """
        self.allowed_types = allowed_types
    
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        msg_type = self._get_message_type(message)
        
        if msg_type not in self.allowed_types:
            types_str = ", ".join(self.allowed_types)
            return False, f"❌ Tipo non valido. Consentiti: {types_str}"
        
        return True, None
    
    def _get_message_type(self, message: Message) -> str:
        """Determina il tipo di messaggio"""
        if message.photo:
            return "photo"
        elif message.document:
            return "document"
        elif message.video:
            return "video"
        elif message.audio:
            return "audio"
        elif message.voice:
            return "voice"
        elif message.text:
            return "text"
        else:
            return "unknown"

class ValidatorChain:
    """Esegue validators in sequenza (AND logic)"""
    
    def __init__(self, validators: List[Validator]):
        self.validators = validators
    
    async def validate(self, message: Message) -> Tuple[bool, Optional[str]]:
        """Valida con tutti i validators. Fallisce al primo errore."""
        for validator in self.validators:
            is_valid, error = await validator.validate(message)
            if not is_valid:
                return False, error
        
        return True, None

# Helper function per creare validator da config
def create_validator_from_question(question_data: dict) -> Validator:
    """
    Crea validator appropriato dalla configurazione domanda.
    
    Args:
        question_data: Dict con "allowed_types", "skippable", etc.
    
    Returns:
        Validator appropriato
    """
    allowed_types = question_data.get("allowed_types", ["text"])
    
    validators = [TypeValidator(allowed_types)]
    
    # Add specific validators based on type
    if "text" in allowed_types:
        validators.append(TextValidator(min_length=1))
    
    return ValidatorChain(validators)
```

**Migrazione**:
```python
# PRIMA (announcement_handler.py)
msg_type = None
if message.text:
    msg_type = "text"
elif message.photo:
    msg_type = "photo"
# ... 20 righe di if/elif

if msg_type not in allowed_types:
    error_msg = await client.send_message(...)
    return

# DOPO
from services.validation_service import create_validator_from_question

validator = create_validator_from_question(question_data)
is_valid, error_msg = await validator.validate(message)

if not is_valid:
    await msg_service.send_error(user_id, error_msg)
    return

# Molto più pulito!
```

**Vantaggi immediati**:
- ✅ Validazione riutilizzabile
- ✅ Facile testare
- ✅ Messaggi errore consistenti
- ✅ Meno codice negli handler

---

## 🔄 Processo di Migrazione (Step by Step)

### **Step 1: Setup Nuova Struttura** (30 min)
```bash
cd source/
mkdir -p core services
touch core/__init__.py core/session_manager.py
touch services/__init__.py services/message_service.py services/validation_service.py
```

### **Step 2: Implementa Session Manager** (1h)
1. Copia codice SessionManager sopra in `core/session_manager.py`
2. Aggiungi import in `core/__init__.py`:
   ```python
   from .session_manager import SessionManager, UserSession, get_session_manager
   ```
3. Test base:
   ```python
   from core.session_manager import get_session_manager
   sm = get_session_manager()
   session = sm.create_session(123, "event")
   print(session)  # Deve printare UserSession
   ```

### **Step 3: Migra un Handler** (2h)
**Target**: `buttons.py` → usa SessionManager

```python
# In buttons.py, PRIMA:
from config import user_data

if data.startswith("new_"):
    cat = data.replace("new_", "")
    user_data[user_id] = {
        "category": cat,
        "step": 0,
        "answers": {},
        # ...
    }

# DOPO:
from core.session_manager import get_session_manager

session_manager = get_session_manager()

if data.startswith("new_"):
    cat = data.replace("new_", "")
    session = session_manager.create_session(user_id, cat)
    # session è già inizializzato con defaults!
```

### **Step 4: Implementa Message Service** (1-2h)
1. Copia codice MessageService in `services/message_service.py`
2. Migra `message_utils.py` per usare MessageService
3. Update `announcement_handler.py`:
   ```python
   # PRIMA
   from .utils.message_utils import safe_delete, send_clean_message
   
   # DOPO
   from services.message_service import MessageService
   msg_service = MessageService(client)
   ```

### **Step 5: Test Completo** (1h)
1. Avvia il bot: `python source/main.py`
2. Testa flow completo:
   - `/start` → Funziona?
   - Nuova categoria → Sessione creata?
   - Rispondi domande → Tracking messaggi?
   - Conferma → Pubblicazione OK?
   - Cleanup → Messaggi eliminati?

3. Verifica log:
   ```bash
   grep "ERROR" logs.txt  # Nessun errore?
   ```

### **Step 6: Commit & Backup**
```bash
git add .
git commit -m "refactor: implement SessionManager and MessageService"
git push
```

---

## 📊 Prima/Dopo

### **Codice PRIMA**
```python
# config.py
user_data = {}  # Global state

# buttons.py
from config import user_data
user_data[user_id] = {"step": 0, "messages_to_delete": []}

# announcement_handler.py  
from config import user_data
msg = await client.send_message(user_id, "Test")
user_data[user_id]["messages_to_delete"].append(msg.id)

# Problema: circular imports, no type safety, manual tracking
```

### **Codice DOPO**
```python
# core/session_manager.py
class SessionManager:
    def create_session(self, user_id, category): ...

# buttons.py
from core.session_manager import get_session_manager
session_manager = get_session_manager()
session = session_manager.create_session(user_id, "event")

# announcement_handler.py
from services.message_service import MessageService
msg_service = MessageService(client)
msg = await msg_service.send_and_track(session, user_id, "Test")

# Vantaggi: no circular imports, type safe, automatic tracking
```

### **Metriche**
| Metrica | Prima | Dopo | Miglioramento |
|---------|-------|------|---------------|
| Import circolari | 3 | 0 | ✅ 100% |
| Righe codice eliminazione messaggi | ~50 | ~10 | ✅ 80% |
| Type safety | ❌ | ✅ | ✅ 100% |
| Testabilità | ❌ | ✅ | ✅ 100% |

---

## 🎯 Prossimi Passi

Dopo questi 3 Quick Wins, hai:
- ✅ Eliminato import circolari
- ✅ Risolto problemi eliminazione messaggi
- ✅ Codice più pulito e testabile

**Prosegui con**:
1. FASE 3 del piano completo (ristrutturazione moduli)
2. FASE 6 (State Machine per announcement flow)
3. FASE 9 (Testing framework)

Oppure fermati qui se vuoi solo fix rapidi! 🚀

---

## 💬 Domande Frequenti

**Q: Posso fare solo Quick Win #1 e fermarmi?**  
A: Sì! Ogni Quick Win è indipendente. Ma raccomando tutti e 3 per massimo beneficio.

**Q: Quanto tempo per tutto?**  
A: 7-9 ore totali (1 giornata lavorativa intensa o 2 giorni tranquilli)

**Q: Rischio di rompere funzionalità?**  
A: Minimo se segui step by step. Testa dopo ogni step. Fai backup/commit frequenti.

**Q: Devo riscrivere tutto?**  
A: No! Questo è refactoring incrementale. Il bot continua a funzionare durante la migrazione.

---

**Inizia ora con Step 1!** 🚀
