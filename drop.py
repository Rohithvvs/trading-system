import psycopg2
from backend.app.config import settings

url = settings.database_url.replace("+asyncpg", "")
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS alembic_version;")
conn.commit()
cur.close()
conn.close()
print("Dropped alembic_version table.")
