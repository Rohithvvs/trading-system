import sqlite3
import datetime

db_path = "backend/trading_system.db"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcUdzNXI2TUhGN3JGTU0zMVpRMDl6bk5HX0IwUV9vVGZFX21VMFozNUtVOGpiWFRxa1lTaFd1ZGtRWVpqOGJ0TFVLT280S3VpU3dLdlF2TEEycFlZcWlNb3FTRWZQOERneW1YM0c4Y2Y0bmtUNXA1UT0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiJlMWYxMTgxMjVlNjgzMDRlYzhkZDI4MDcxM2UyNjk4Y2EwZmE1YmQ5OWMyNjUwN2RjZDA1OTAyMyIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWUowODcxOCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzgwMTg3NDAwLCJpYXQiOjE3ODAxNDE2NzUsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc4MDE0MTY3NSwic3ViIjoiYWNjZXNzX3Rva2VuIn0.CrnUoNRe5EfKH-TzXTaXU3vdZUxh2fA8xWVERUrBUcM"

now = datetime.datetime.utcnow().isoformat()
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # The table might not have an id column or constraint, so let's just clear and insert.
    cursor.execute("DELETE FROM fyers_auth")
    cursor.execute("""
    INSERT INTO fyers_auth (access_token, is_active, created_at, updated_at)
    VALUES (?, 1, ?, ?)
    """, (token, now, now))
    conn.commit()
    print("Token updated successfully.")
except Exception as e:
    print("Error:", e)
finally:
    if 'conn' in locals():
        conn.close()
