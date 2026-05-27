import os
import sys
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run():
    db_path = r"F:\trading system01\trading system\trading_system.db"
    print(f"Modifying DB at {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE historical_candles ADD COLUMN resolution VARCHAR(20) DEFAULT '1D' NOT NULL")
        print("Added resolution column.")
    except Exception as e:
        print(f"Error: {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    run()
