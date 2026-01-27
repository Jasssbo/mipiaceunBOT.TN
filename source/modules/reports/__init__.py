"""
Gestione dei report e segnalazioni degli utenti.
"""
from .report_user import (
    add_report,
    count_reports_for_user,
    load_reports,
    save_reports
)

# Note: report_user_handler è registrato come handler e non va importato

__all__ = [
    'add_report',
    'count_reports_for_user',
    'load_reports',
    'save_reports'
]