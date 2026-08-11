"""
API principale del bot MiPiaceUnBOT.TN.
Questo file espone tutte le funzionalità pubbliche del bot.
"""
from .core import send_main_menu

from .permissions import is_user_allowed_by_username

from .reports import (
    add_report,
    count_unique_reporters_for_user,
    load_reports,
    save_reports,
    apply_retention_policy
)

from .user_announcements_interactions import (
    # Announcement handling
    send_preview,
    update_preview_with_id,
    publish_announcement,
    build_announcement_text,
    # Message utilities
    send_clean_message,
    safe_delete
)

__all__ = [
    # Core functionality
    'send_main_menu',
    
    # Permissions
    'is_user_allowed_by_username',
    
    # Reports
    'add_report',
    'count_unique_reporters_for_user',
    'load_reports',
    'save_reports',
    'apply_retention_policy',
    
    # Announcements
    'send_preview',
    'update_preview_with_id',
    'publish_announcement',
    'build_announcement_text',
    'send_clean_message',
    'safe_delete'
]