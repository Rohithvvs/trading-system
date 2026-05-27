from app.db.session import engine, init_db
from app.db.base import Base

try:
    print("Initializing DB...")
    init_db()
    print("DB initialized successfully. Tables in metadata:")
    for table_name in Base.metadata.tables.keys():
        print(f" - {table_name}")
except Exception as e:
    import traceback
    traceback.print_exc()
