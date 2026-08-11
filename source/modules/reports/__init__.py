"""
Gestione dei report e segnalazioni degli utenti.
"""
from .report_user import (
    add_report,
    count_unique_reporters_for_user,
    load_reports,
    save_reports,
    apply_retention_policy
)

# Note: report_user_handler è registrato come handler e non va importato
# Note: admin handlers sono registrati come handler e non vanno importati

__all__ = [
    'add_report',
    'count_unique_reporters_for_user',
    'load_reports',
    'save_reports',
    'apply_retention_policy'
]