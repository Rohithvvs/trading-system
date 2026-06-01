import sqlalchemy as sa
from app.config import settings

engine = sa.create_engine(settings.database_url.replace('+asyncpg', ''))
with engine.connect() as c:
    print(c.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='market_data' AND table_name LIKE 'candles_1d%'")).fetchall())
