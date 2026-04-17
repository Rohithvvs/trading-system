import sqlite3

conn = sqlite3.connect("trading_system.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    source TEXT,
    url TEXT UNIQUE,
    published_at TEXT,
    summary TEXT
)
""")

conn.commit()
conn.close()

print("SQLite database and table created.")
