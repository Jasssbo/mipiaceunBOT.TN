"""
Utility per la gestione dei messaggi e altre funzionalità di supporto.
"""
from .message_utils import safe_delete, send_clean_message

__all__ = ['safe_delete', 'send_clean_message']