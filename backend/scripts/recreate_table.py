import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.db.session import engine
from backend.app.models.market_data import HistoricalCandle

def run():
    print("Dropping HistoricalCandle table...")
    HistoricalCandle.__table__.drop(engine, checkfirst=True)
    print("Recreating HistoricalCandle table...")
    HistoricalCandle.__table__.create(engine)
    print("Done!")

if __name__ == "__main__":
    run()
