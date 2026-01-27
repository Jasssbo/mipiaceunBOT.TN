"""
Funzionalità core del bot, include gestione bottoni e comandi base.
"""
from modules.core.buttons import send_main_menu

# Note: buttons_callback_handler è registrato come handler e non va importato
# start_handler è registrato come handler e non va importato

__all__ = [
    'send_main_menu'
]