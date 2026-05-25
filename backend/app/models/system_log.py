from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from ..db.base import Base

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String, index=True)
    module = Column(String, index=True)
    endpoint = Column(String, nullable=True)
    message = Column(String)
    traceback = Column(Text, nullable=True)
