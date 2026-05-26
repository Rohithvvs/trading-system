from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from ..db.base import Base

class HistoricalCandle(Base):
    __tablename__ = "historical_candles"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    timeframe = Column(String, index=True, nullable=False)  # e.g., '1D', '15T'
    timestamp = Column(DateTime, index=True, nullable=False)  # Strictly UTC naive
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uix_symbol_timeframe_timestamp"),
    )
