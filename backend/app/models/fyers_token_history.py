from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from ..db.base import Base


class FyersTokenHistory(Base):
    __tablename__ = "fyers_token_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token_masked = Column(String)
    saved_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="active")
    note = Column(String, nullable=True)
