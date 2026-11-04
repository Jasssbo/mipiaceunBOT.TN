import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func, delete, or_, text
from .models import Base, Report

# Anchor default SQLite file to repository root (/app/users_data.db)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_FILE = _PROJECT_ROOT / "users_data.db"
DB_PATH = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{_DEFAULT_DB_FILE}")

engine = create_async_engine(DB_PATH, echo=False)
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

_db_initialized = False


async def init_db() -> None:
    """Inizializza le tabelle del database in modo idempotente e ottimizza SQLite (WAL + cache limitata)."""
    global _db_initialized
    if _db_initialized:
        return
    async with engine.begin() as conn:
        if DB_PATH.startswith("sqlite"):
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            await conn.execute(text("PRAGMA busy_timeout=5000;"))
            await conn.execute(text("PRAGMA cache_size=-4000;"))  # Max ~4MB RAM cache per SQLite
        await conn.run_sync(Base.metadata.create_all)
    _db_initialized = True


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_initialized(self) -> None:
        if self.session.bind is engine:
            await init_db()

    async def add(self, report: Report) -> Report:
        await self._ensure_initialized()
        self.session.add(report)
        await self.session.commit()
        return report

    async def get_count_for_user(self, user_id: int) -> int:
        await self._ensure_initialized()
        result = await self.session.execute(
            select(func.count()).where(Report.reported_user_id == user_id)
        )
        return result.scalar() or 0

    async def count_unique_reporters_for_user(self, user_id: int) -> int:
        await self._ensure_initialized()
        result = await self.session.execute(
            select(func.count(func.distinct(Report.reporter_user_id)))
            .where(Report.reported_user_id == user_id)
        )
        return result.scalar() or 0

    async def count_reports_today_by_user(self, reporter_id: int) -> int:
        await self._ensure_initialized()
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        result = await self.session.execute(
            select(func.count())
            .where(Report.reporter_user_id == reporter_id)
            .where(Report.timestamp >= today_start)
        )
        return result.scalar() or 0

    async def has_already_reported(self, reporter_id: int, reported_user_id: int) -> bool:
        await self._ensure_initialized()
        result = await self.session.execute(
            select(func.count())
            .where(Report.reporter_user_id == reporter_id)
            .where(Report.reported_user_id == reported_user_id)
        )
        return (result.scalar() or 0) > 0

    async def apply_retention_policy(self, days: int) -> int:
        await self._ensure_initialized()
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        result = await self.session.execute(
            delete(Report).where(Report.timestamp < cutoff)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def get_reports_for_user(self, user_id: int):
        await self._ensure_initialized()
        result = await self.session.execute(
            select(Report).where(
                or_(
                    Report.reporter_user_id == user_id,
                    Report.reported_user_id == user_id,
                )
            )
        )
        return result.scalars().all()

    async def erase_user_data(self, user_id: int) -> int:
        await self._ensure_initialized()
        result = await self.session.execute(
            delete(Report).where(
                or_(
                    Report.reporter_user_id == user_id,
                    Report.reported_user_id == user_id,
                )
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def get_recent_reports(self, limit: int = 20):
        await self._ensure_initialized()
        result = await self.session.execute(
            select(Report).order_by(Report.timestamp.desc()).limit(limit)
        )
        return result.scalars().all()

    async def clear_user_reports(self, reported_user_id: int) -> int:
        await self._ensure_initialized()
        result = await self.session.execute(
            delete(Report).where(Report.reported_user_id == reported_user_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def get_total_count(self) -> int:
        await self._ensure_initialized()
        result = await self.session.execute(select(func.count(Report.id)))
        return result.scalar() or 0


async def get_repository():
    """Dependency per ottenere il repository con una nuova sessione."""
    await init_db()
    async with async_session() as session:
        yield ReportRepository(session)
