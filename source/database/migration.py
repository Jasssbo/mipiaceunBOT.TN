import asyncio
import json
import os
from database.repository import init_db, DB_PATH, async_session, ReportRepository
from database.models import Report
from datetime import datetime

REPORTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../reports.json'))

async def run_migration():
    await init_db()
    
    if not os.path.exists(REPORTS_FILE):
        print(f"File {REPORTS_FILE} non trovato. Nessuna migrazione necessaria.")
        return
        
    with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
        try:
            reports_data = json.load(f)
        except json.JSONDecodeError:
            print(f"Errore: Il file {REPORTS_FILE} è corrotto.")
            return

    async with async_session() as session:
        repo = ReportRepository(session)
        count = 0
        for data in reports_data:
            report_time_str = data.get('timestamp')
            report_time = datetime.utcnow()
            if report_time_str:
                try:
                    report_time = datetime.fromisoformat(report_time_str)
                except ValueError:
                    pass
            
            report = Report(
                reported_username=data.get('reported_username') or data.get('reported_user'),
                reported_user_id=data.get('reported_user_id'),
                reporter_username=data.get('reporter_username') or data.get('reporter'),
                reporter_user_id=data.get('reporter_id'),
                reason=data.get('reason'),
                timestamp=report_time
            )
            await repo.add(report)
            count += 1
            
    print(f"Migrazione completata. {count} report trasferiti nel database.")

if __name__ == "__main__":
    asyncio.run(run_migration())
