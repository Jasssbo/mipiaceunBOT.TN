import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from .models import Base, Report

DB_PATH = "sqlite+aiosqlite:///users_data.db"

engine = create_async_engine(DB_PATH, echo=False)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add(self, report: Report) -> Report:
        self.session.add(report)
        await self.session.commit()
        return report
    
    async def get_count_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).where(Report.reported_user_id == user_id)
        )
        return result.scalar()
        
    async def count_unique_reporters_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(Report.reporter_user_id)))
            .where(Report.reported_user_id == user_id)
        )
        return result.scalar()
        
    async def count_reports_today_by_user(self, reporter_id: int) -> int:
        from datetime import datetime
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count())
            .where(Report.reporter_user_id == reporter_id)
            .where(Report.timestamp >= today_start)
        )
        return result.scalar()
        
    async def has_already_reported(self, reporter_id: int, reported_user_id: int) -> bool:
        result = await self.session.execute(
            select(func.count())
            .where(Report.reporter_user_id == reporter_id)
            .where(Report.reported_user_id == reported_user_id)
        )
        return result.scalar() > 0
        
    async def apply_retention_policy(self, days: int) -> int:
        from datetime import datetime, timedelta
        from sqlalchemy import delete
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            delete(Report).where(Report.timestamp < cutoff)
        )
        await self.session.commit()
        return result.rowcount

    async def get_reports_for_user(self, user_id: int):
        from sqlalchemy import or_
        result = await self.session.execute(
            select(Report).where(
                or_(
                    Report.reporter_user_id == user_id,
                    Report.reported_user_id == user_id
                )
            )
        )
        return result.scalars().all()
        
    async def erase_user_data(self, user_id: int) -> int:
        from sqlalchemy import delete, or_
        result = await self.session.execute(
            delete(Report).where(
                or_(
                    Report.reporter_user_id == user_id,
                    Report.reported_user_id == user_id
                )
            )
        )
        await self.session.commit()
        return result.rowcount
        
    async def get_recent_reports(self, limit: int = 20):
        result = await self.session.execute(
            select(Report).order_by(Report.timestamp.desc()).limit(limit)
        )
        return result.scalars().all()
        
    async def clear_user_reports(self, reported_user_id: int) -> int:
        from sqlalchemy import delete
        result = await self.session.execute(
            delete(Report).where(Report.reported_user_id == reported_user_id)
        )
        await self.session.commit()
        return result.rowcount
        
    async def get_total_count(self) -> int:
        result = await self.session.execute(select(func.count(Report.id)))
        return result.scalar()
async def get_repository():
    """Dependency per ottenere il repository con una nuova sessione."""
    await init_db()
    async with async_session() as session:
        yield ReportRepository(session)
