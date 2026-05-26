from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from ..db.base import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_utc_now, index=True)
    level = Column(String, index=True)
    source = Column(String, index=True)
    module = Column(String, index=True)
    endpoint = Column(String, nullable=True)
    message = Column(String)
    error_hash = Column(String, index=True, nullable=True)
    traceback = Column(Text, nullable=True)
    structured_data = Column(JSON, nullable=True)
    correlationId = Column(String, index=True, nullable=True)
    userId = Column(String, index=True, nullable=True)
    symbol = Column(String, index=True, nullable=True)
    orderId = Column(String, index=True, nullable=True)
    environment = Column(String, default="DEV", index=True)
