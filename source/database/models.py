from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utc_now() -> datetime:
    """Restituisce il timestamp UTC corrente (naive per compatibilità SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reported_username = Column(String, index=True)
    reported_user_id = Column(BigInteger, index=True)
    reporter_username = Column(String)
    reporter_user_id = Column(BigInteger, index=True)
    reason = Column(Text)
    timestamp = Column(DateTime, default=_utc_now)
