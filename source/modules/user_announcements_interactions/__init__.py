"""
Gestione delle interazioni utente relative agli annunci.
Include la raccolta dati, la compilazione e la pubblicazione degli annunci.
"""
from .announcement_handler import (
    send_preview,
    update_preview_with_id,
    publish_announcement,
    build_announcement_text,
    start_compilation_timeout,
    cleanup_user_data_and_messages
)

from .utils import (
    send_clean_message,
    safe_delete
)

__all__ = [
    # Funzionalità di gestione annunci
    'send_preview',
    'update_preview_with_id',
    'publish_announcement',
    'build_announcement_text',
    'start_compilation_timeout',
    'cleanup_user_data_and_messages',
    
    # Utility di gestione messaggi
    'send_clean_message',
    'safe_delete'
]