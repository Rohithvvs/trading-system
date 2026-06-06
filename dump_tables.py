from backend.app.db.base import Base
from backend.app.models import analysis, fyers_token, market_data, paper_trading, stock, system_log, workstation

print("TABLES:", list(Base.metadata.tables.keys()))
