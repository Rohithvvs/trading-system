import sqlite3

db_path = r"F:\trading system01\trading system\backend\data\scan_result.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT * FROM latest_scan;")
row = cursor.fetchone()
print("latest_scan columns:")
for col in cursor.description:
    print(col[0])
print("Value preview:", str(row)[:500])

conn.close()
