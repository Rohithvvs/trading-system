import os
from pathlib import Path

def safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed {path}")
    except Exception as e:
        print(f"Error removing {path}: {e}")

root = Path(__file__).parent
safe_remove(root / "backend" / "app" / "db" / "scan_result.db")
safe_remove(root / "tests" / "artifacts" / "backend" / "test_app.db")
safe_remove(root / "backend" / "test.db")
safe_remove(root / "test.db")
