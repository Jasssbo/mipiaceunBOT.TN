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

from config import MAX_INPUT_LENGTH

def create_validator_from_question(question_data: dict) -> Validator:
    """
    Crea validator appropriato dalla configurazione domanda.
    """
    allowed_types = question_data.get("allowed_types", ["text"])
    
    validators = [TypeValidator(allowed_types)]
    
    if "text" in allowed_types:
        validators.append(TextValidator(min_length=1, max_length=MAX_INPUT_LENGTH))
    
    return ValidatorChain(validators)
