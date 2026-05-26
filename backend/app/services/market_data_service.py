import pandas as pd
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy import select
from ..db.session import SessionLocal, engine
from ..models.market_data import HistoricalCandle

class MarketDataService:
    def get_latest_candle_time(self, symbol: str, timeframe: str) -> datetime | None:
        with SessionLocal() as db:
            stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.timeframe == timeframe
            ).order_by(HistoricalCandle.timestamp.desc()).limit(1)
            result = db.execute(stmt).scalar_one_or_none()
            return result

    def upsert_candles(self, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        if candles_df is None or candles_df.empty:
            return

        records = []
        for index, row in candles_df.iterrows():
            dt = index
            if hasattr(dt, "to_pydatetime"):
                dt = dt.to_pydatetime()
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
                
            records.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": dt,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"])
            })

        with SessionLocal() as db:
            stmt = insert(HistoricalCandle).values(records)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["symbol", "timeframe", "timestamp"]
            )
            db.execute(stmt)
            db.commit()

    def load_full_history(self, symbol: str, timeframe: str) -> pd.DataFrame:
        query = select(
            HistoricalCandle.timestamp.label("date"),
            HistoricalCandle.open,
            HistoricalCandle.high,
            HistoricalCandle.low,
            HistoricalCandle.close,
            HistoricalCandle.volume
        ).where(
            HistoricalCandle.symbol == symbol,
            HistoricalCandle.timeframe == timeframe
        ).order_by(HistoricalCandle.timestamp.asc())
        
        df = pd.read_sql_query(query, engine)
        if not df.empty:
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
        return df
