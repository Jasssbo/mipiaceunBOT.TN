"""
Gestione delle autorizzazioni e della sicurezza nel bot.
"""
from .user_permissions import is_user_allowed_by_username

__all__ = [
    'is_user_allowed_by_username'
]