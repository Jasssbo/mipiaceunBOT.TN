from datetime import datetime
import asyncio
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    reported_username = Column(String, index=True)
    reported_user_id = Column(Integer)
    reporter_username = Column(String)
    reporter_user_id = Column(Integer)
    reason = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
