from sqlalchemy import Column, Integer, String, DateTime

from ..db.base import Base
from ..utils.datetime_utils import utc_now


class FyersTokenHistory(Base):
    __tablename__ = "fyers_token_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token_masked = Column(String)
    saved_at = Column(DateTime(timezone=True), default=utc_now)
    status = Column(String, default="active")
    note = Column(String, nullable=True)
