import sys
import os
import json
from datetime import datetime

# Adjust Python path to import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from app.db.base import Base
import app.models  # This will import all models and register them with Base.metadata

def generate_markdown():
    tables = Base.metadata.tables
    
    md = ["# Database Schema Export\n", "This document contains an analysis of all SQLAlchemy models and database tables.\n"]
    
    for table_name, table in sorted(tables.items()):
        md.append(f"## Table: `{table_name}`\n")
        
        # Purpose (heuristics based on table name)
        purpose = f"Stores data for {table_name.replace('_', ' ')}."
        md.append(f"- **Purpose**: {purpose}\n")
        
        # Columns & Types
        md.append("- **Columns & Types**:")
        for col in table.columns:
            nullable_str = "Nullable" if col.nullable else "Not Null"
            pk_str = ", Primary Key" if col.primary_key else ""
            md.append(f"  - `{col.name}` ({col.type}): {nullable_str}{pk_str}")
        
        # Indexes
        md.append("- **Indexes**:")
        if table.indexes:
            for idx in table.indexes:
                cols = ", ".join([c.name for c in idx.columns])
                unique_str = " (Unique)" if idx.unique else ""
                md.append(f"  - `{idx.name}` on [{cols}]{unique_str}")
        else:
            md.append("  - None")
            
        # Constraints & Foreign Keys
        md.append("- **Constraints**:")
        constraints = []
        for fk in table.foreign_keys:
            constraints.append(f"Foreign Key `{fk.column.name}` -> `{fk.target_fullname}`")
        for c in table.constraints:
            if type(c).__name__ not in ('PrimaryKeyConstraint', 'ForeignKeyConstraint'):
                constraints.append(f"{type(c).__name__}: {c.name}")
        
        if constraints:
            for c in constraints:
                md.append(f"  - {c}")
        else:
            md.append("  - None")
            
        # Relationships (from SQLAlchemy ORM, hard to extract generically from Table, skipping explicit relations, FKs cover it)
        md.append(f"- **Relationships**: Managed via Foreign Keys above.\n")
        
        # Used Services
        md.append(f"- **Used Services**: Backend API, {table_name.split('_')[0].capitalize()} Services.\n")
        
        # Data Lifecycle
        lifecycle = "Created by application logic. Updated as needed. "
        if "log" in table_name or "history" in table_name or "event" in table_name:
            lifecycle = "Append-only. Rarely updated or deleted. Maintained for historical records."
        elif "session" in table_name:
            lifecycle = "Created on start, updated during lifecycle, potentially purged after expiration."
        md.append(f"- **Data Lifecycle**: {lifecycle}\n")
        
        # Example Record
        md.append("- **Example Records**:")
        example = {}
        for col in table.columns:
            if "int" in str(col.type).lower() or "numeric" in str(col.type).lower():
                example[col.name] = 1
            elif "datetime" in str(col.type).lower():
                example[col.name] = "2023-10-01T12:00:00Z"
            elif "bool" in str(col.type).lower():
                example[col.name] = True
            else:
                example[col.name] = "example_string"
        md.append(f"  ```json\n  {json.dumps(example, indent=2)}\n  ```\n")
        md.append("---\n")
    
    # Also add alembic_version
    md.append("## Table: `alembic_version`\n")
    md.append("- **Purpose**: Alembic migration tracking table.\n")
    md.append("- **Columns & Types**:\n  - `version_num` (String): Not Null, Primary Key\n")
    md.append("- **Indexes**:\n  - None\n")
    md.append("- **Constraints**:\n  - None\n")
    md.append("- **Relationships**: None\n")
    md.append("- **Used Services**: Alembic Migrations\n")
    md.append("- **Data Lifecycle**: Updated automatically by Alembic during schema migrations.\n")
    md.append("- **Example Records**:\n  ```json\n  {\n    \"version_num\": \"6650a54dd6aa\"\n  }\n  ```\n")
    md.append("---\n")
        
    out_path = r"F:\trading system01\trading system\docs\notebooklm_assets\database_schema_export.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
        
    print(f"Generated successfully at {out_path}")

if __name__ == "__main__":
    generate_markdown()
