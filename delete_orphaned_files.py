import os
import shutil
from pathlib import Path

root = Path(__file__).parent

files_to_delete = [
    root / "frontend" / "src" / "components" / "Login.tsx",
    root / "frontend" / "src" / "contexts" / "AuthContext.tsx",
    root / "backend" / "app" / "models" / "user.py",
]

for file_path in files_to_delete:
    if file_path.exists() and file_path.is_file():
        os.remove(file_path)
        print(f"Deleted: {file_path}")
    else:
        print(f"Not found or already deleted: {file_path}")

# Clean pycache and pytest_cache
for root_dir, dirs, files in os.walk(root):
    for d in list(dirs):
        if d in ["__pycache__", ".pytest_cache"]:
            dir_path = Path(root_dir) / d
            shutil.rmtree(dir_path)
            print(f"Deleted directory: {dir_path}")
            dirs.remove(d) # Don't traverse into it
