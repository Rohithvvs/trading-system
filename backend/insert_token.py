import sqlite3
from datetime import datetime

# Path to your local SQLite file
DB_PATH = "./trading_system.db"

# Put your actual token inside these quotes
MY_TOKEN = "PASTE_YOUR_TOKEN_HERE" 

def inject_token():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clean out any old broken rows just in case
    cursor.execute("DELETE FROM fyers_tokens")
    
    # Insert the fresh token row for your default_user
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO fyers_tokens (user_id, access_token, created_at, updated_at)
        VALUES (?, ?, ?, ?)
    """, ("default_user", MY_TOKEN, now, now))
    
    conn.commit()
    conn.close()
    print("🚀 Token injected successfully into trading_system.db!")

if __name__ == "__main__":
    inject_token()