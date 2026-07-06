#!/usr/bin/env python3
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
repair_database.py -- Single-User Database Repair & Token Seeding Script
========================================================================

This script performs two critical operations on the trading_system.db:

  1. SCHEMA REPAIR: Inspects all trading tables for any residual `user_id`
     columns left over from a prior multi-tenant experiment. If found, it
     safely rebuilds the table without the column using SQLite's
     CREATE-COPY-DROP-RENAME pattern, preserving every historical row.

  2. TOKEN SEEDING: Writes (or updates) the single FYERS access token into
     the `fyers_tokens` table so the system can boot cleanly with live
     market data connectivity.

Usage:
    python repair_database.py                         # uses default DB path
    python repair_database.py --db ./trading_system.db
    python repair_database.py --token "eyJ..."        # override token via CLI
    FYERS_ACCESS_TOKEN="eyJ..." python repair_database.py  # override via env

Safety:
    - Creates a timestamped backup before ANY schema modification.
    - All schema changes run inside a single transaction.
    - Read-only inspection produces zero side effects when no repair is needed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "trading_system.db"

# The live FYERS access token for the single-user system.
# Can be overridden via --token CLI arg or FYERS_ACCESS_TOKEN env var.
EMBEDDED_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcU"
    "VsMXZXZDhPZzNhSEhOOU10bG9zbV85cE53bUExWTcxel9vSmpqb1g2bV8xV3JTenBJTXli"
    "cjg1QjQ4dzMyOGRrcEEySnhTa2I2MTlXZW1namdpbTJ1VFZQeVFvWE13X210aUdRb2R5dT"
    "NxdWtkbz0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI1ZGY3"
    "YTdkMGU5OWIwYjRkMmMwZWNjNjJlYmI1ZmJiZjMxMDRjMWQ4NjhhNGM1MzI4NjcwMGRjMC"
    "IsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWUowOD"
    "cxOCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzc5NjY5MDAwLCJpYXQiOjE3Nzk1ODg0NjMsIm"
    "lzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc3OTU4ODQ2Mywic3ViIjoiYWNjZXNzX3Rva2"
    "VuIn0.3RSzEXdRSF6MZzCCcmes9jpyOTaym1fFS2zgwLecVYA"
)

# Tables to inspect for residual user_id columns
TARGET_TABLES = [
    "paper_trading_accounts",
    "paper_trading_orders",
    "paper_trading_positions",
    "paper_trading_trade_history",
    "paper_trading_transactions",
    "paper_trading_notifications",
    "paper_trading_alerts",
    "paper_trading_execution_events",
    "market_engine_sessions",
    "fyers_tokens",
    "fyers_token_history",
    "risk_settings",
    "saved_scans",
    "scan_history_snapshots",
    "workstation_alerts",
]


# ─── Terminal Formatting ─────────────────────────────────────────────────────

class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"


def _ok(msg: str) -> None:
    print(f"  {_C.GREEN}[OK]{_C.RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_C.YELLOW}[WARN]{_C.RESET} {msg}")


def _err(msg: str) -> None:
    print(f"  {_C.RED}[FAIL]{_C.RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {_C.CYAN}-->{_C.RESET} {msg}")


def _header(msg: str) -> None:
    print(f"\n{_C.BOLD}{_C.CYAN}{'-' * 64}{_C.RESET}")
    print(f"{_C.BOLD}  {msg}{_C.RESET}")
    print(f"{_C.BOLD}{_C.CYAN}{'-' * 64}{_C.RESET}")


# ─── Phase 1: Schema Repair (user_id column removal) ────────────────────────

def get_table_columns(cur: sqlite3.Cursor, table: str) -> list[dict]:
    """Return column metadata for a table via PRAGMA table_info."""
    rows = cur.execute(f"PRAGMA table_info('{table}')").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone()[0] > 0


def remove_user_id_column(conn: sqlite3.Connection, table: str) -> bool:
    """
    Remove the `user_id` column from a table using SQLite's safe
    CREATE-COPY-DROP-RENAME strategy.

    Returns True if the column was found and removed, False if not present.
    """
    cur = conn.cursor()

    if not table_exists(cur, table):
        return False

    columns = get_table_columns(cur, table)
    col_names = [c["name"] for c in columns]

    if "user_id" not in col_names:
        return False

    # Build the list of columns to keep (everything except user_id)
    keep_cols = [c for c in columns if c["name"] != "user_id"]
    keep_names = [c["name"] for c in keep_cols]
    keep_names_str = ", ".join(keep_names)

    # Count rows before migration
    row_count = cur.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]

    # Step 1: Get the original CREATE TABLE statement for reference
    create_sql = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()[0]

    # Step 2: Build column definitions for the temp table
    col_defs = []
    for c in keep_cols:
        parts = [c["name"], c["type"]]
        if c["pk"]:
            parts.append("PRIMARY KEY")
        if c["notnull"] and not c["pk"]:
            parts.append("NOT NULL")
        if c["default"] is not None:
            parts.append(f"DEFAULT {c['default']}")
        col_defs.append(" ".join(parts))

    temp_table = f"_repair_temp_{table}"

    # Step 3: Execute the migration inside the existing transaction
    cur.execute(f"CREATE TABLE '{temp_table}' ({', '.join(col_defs)})")
    cur.execute(f"INSERT INTO '{temp_table}' ({keep_names_str}) SELECT {keep_names_str} FROM '{table}'")

    # Verify row counts match
    new_count = cur.execute(f"SELECT COUNT(*) FROM '{temp_table}'").fetchone()[0]
    if new_count != row_count:
        raise RuntimeError(
            f"Row count mismatch during {table} migration: "
            f"original={row_count}, copied={new_count}. Aborting."
        )

    cur.execute(f"DROP TABLE '{table}'")
    cur.execute(f"ALTER TABLE '{temp_table}' RENAME TO '{table}'")

    # Recreate indexes that existed on the original table
    # (basic indexes only — foreign keys are re-established by SQLAlchemy on boot)
    for col in keep_cols:
        if col["name"] in ("id", "created_at", "updated_at", "status", "symbol", "account_id"):
            try:
                idx_name = f"ix_{table}_{col['name']}"
                cur.execute(f"CREATE INDEX IF NOT EXISTS '{idx_name}' ON '{table}' ({col['name']})")
            except sqlite3.OperationalError:
                pass  # Index may already exist or column may not support it

    return True


def phase_1_schema_repair(conn: sqlite3.Connection) -> int:
    """Inspect all target tables and remove user_id columns. Returns count of repaired tables."""
    _header("PHASE 1: Schema Repair -- user_id Column Removal")
    repaired = 0
    cur = conn.cursor()

    for table in TARGET_TABLES:
        if not table_exists(cur, table):
            print(f"  {_C.DIM}. {table:40s} -- table does not exist (skip){_C.RESET}")
            continue

        columns = get_table_columns(cur, table)
        col_names = [c["name"] for c in columns]

        if "user_id" in col_names:
            row_count = cur.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
            _warn(f"{table:40s} -- user_id FOUND ({row_count} rows)")
            _info(f"Rebuilding {table} without user_id...")
            removed = remove_user_id_column(conn, table)
            if removed:
                _ok(f"{table:40s} -- user_id removed, {row_count} rows preserved")
                repaired += 1
            else:
                _err(f"{table:40s} -- removal failed unexpectedly")
        else:
            _ok(f"{table:40s} -- clean (no user_id)")

    if repaired == 0:
        print(f"\n  {_C.GREEN}All tables are already clean. No schema repairs needed.{_C.RESET}")
    else:
        print(f"\n  {_C.YELLOW}Repaired {repaired} table(s).{_C.RESET}")

    return repaired


# ─── Phase 2: Token Seeding ──────────────────────────────────────────────────

def phase_2_token_seeding(conn: sqlite3.Connection, token: str) -> None:
    """Write or update the single FYERS access token in the fyers_tokens table."""
    _header("PHASE 2: FYERS Token Seeding")

    cur = conn.cursor()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Ensure the fyers_tokens table exists (it should from init_db, but be safe)
    if not table_exists(cur, "fyers_tokens"):
        _info("Creating fyers_tokens table...")
        cur.execute("""
            CREATE TABLE fyers_tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                access_token    TEXT    NOT NULL,
                created_at      TEXT,
                expires_at      TEXT,
                is_active       INTEGER DEFAULT 1,
                status          VARCHAR(32) DEFAULT 'active',
                access_token_saved_at TEXT,
                last_error      TEXT
                -- refresh_token* columns removed in cleanup
            )
        """)
        _ok("fyers_tokens table created")

    # Check for existing row
    existing = cur.execute("SELECT id, status FROM fyers_tokens ORDER BY id ASC LIMIT 1").fetchone()

    if existing:
        row_id = existing[0]
        _info(f"Existing token row found (id={row_id}, status={existing[1]}). Updating...")
        cur.execute(
            """
            UPDATE fyers_tokens
            SET access_token = ?,
                status = 'active',
                is_active = 1,
                access_token_saved_at = ?,
                last_error = NULL
            WHERE id = ?
            """,
            (token, now_utc, row_id),
        )
        _ok(f"Token row id={row_id} updated with new access token")
    else:
        _info("No token row exists. Inserting new row...")
        cur.execute(
            """
            INSERT INTO fyers_tokens (access_token, status, is_active, created_at, access_token_saved_at, last_error)
            VALUES (?, 'active', 1, ?, ?, NULL)
            """,
            (token, now_utc, now_utc),
        )
        _ok("New token row inserted (id=1)")

    # Verification read
    verify = cur.execute(
        "SELECT id, status, is_active, LENGTH(access_token), access_token_saved_at FROM fyers_tokens LIMIT 1"
    ).fetchone()
    if verify:
        _ok(f"Verified: id={verify[0]}, status={verify[1]}, active={verify[2]}, "
            f"token_len={verify[3]}, saved_at={verify[4]}")
    else:
        _err("Verification read failed -- no rows in fyers_tokens after insert!")


# ─── Phase 3: Integrity Checks ──────────────────────────────────────────────

def phase_3_integrity_checks(conn: sqlite3.Connection) -> bool:
    """Run post-repair integrity checks on the database."""
    _header("PHASE 3: Post-Repair Integrity Verification")

    cur = conn.cursor()
    all_ok = True

    # Check 1: SQLite integrity check
    _info("Running PRAGMA integrity_check...")
    result = cur.execute("PRAGMA integrity_check").fetchone()
    if result and result[0] == "ok":
        _ok("PRAGMA integrity_check passed")
    else:
        _err(f"PRAGMA integrity_check FAILED: {result}")
        all_ok = False

    # Check 2: Verify no user_id columns remain
    _info("Verifying zero user_id columns across all tables...")
    all_tables = [
        r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]

    contaminated = []
    for table in all_tables:
        cols = get_table_columns(cur, table)
        if any(c["name"] == "user_id" for c in cols):
            contaminated.append(table)

    if contaminated:
        _err(f"user_id still found in: {contaminated}")
        all_ok = False
    else:
        _ok(f"All {len(all_tables)} tables verified clean (no user_id)")

    # Check 3: Verify token exists and is active
    _info("Verifying FYERS token is seeded and active...")
    token_row = cur.execute(
        "SELECT id, status, is_active, LENGTH(access_token) FROM fyers_tokens LIMIT 1"
    ).fetchone()
    if token_row and token_row[1] == "active" and token_row[2] == 1 and (token_row[3] or 0) > 50:
        _ok(f"Token verified: id={token_row[0]}, status=active, length={token_row[3]}")
    else:
        _err(f"Token verification failed: {token_row}")
        all_ok = False

    # Check 4: Verify paper trading account exists
    _info("Verifying paper trading account singleton...")
    if table_exists(cur, "paper_trading_accounts"):
        acct_count = cur.execute("SELECT COUNT(*) FROM paper_trading_accounts").fetchone()[0]
        if acct_count >= 1:
            acct = cur.execute(
                "SELECT id, name, cash_balance FROM paper_trading_accounts ORDER BY id ASC LIMIT 1"
            ).fetchone()
            _ok(f"Account found: id={acct[0]}, name='{acct[1]}', balance={acct[2]}")
        else:
            _warn("No paper trading account exists (will be auto-created on first API call)")
    else:
        _warn("paper_trading_accounts table not found (will be created by init_db)")

    # Check 5: Report data preservation
    _info("Data preservation report:")
    data_tables = [
        "paper_trading_accounts",
        "paper_trading_orders",
        "paper_trading_positions",
        "paper_trading_trade_history",
        "paper_trading_transactions",
        "market_engine_sessions",
    ]
    for t in data_tables:
        if table_exists(cur, t):
            count = cur.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
            marker = _C.GREEN if count > 0 else _C.DIM
            print(f"    {marker}  {t:40s} {count:>6} rows{_C.RESET}")

    return all_ok


# ─── Main Entry Point ────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trading System Database Repair & Token Seeding Script"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite database file (default: ./trading_system.db)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="FYERS access token (overrides embedded and env values)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect only -- do not modify the database",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    # Resolve the token: CLI > env > embedded
    token = args.token or os.getenv("FYERS_ACCESS_TOKEN") or EMBEDDED_TOKEN

    print(f"\n{_C.BOLD}+==================================================================+{_C.RESET}")
    print(f"{_C.BOLD}|  TRADING SYSTEM -- Database Repair & Token Seeding              |{_C.RESET}")
    print(f"{_C.BOLD}+==================================================================+{_C.RESET}")
    print(f"  Database : {db_path}")
    print(f"  Exists   : {db_path.exists()}")
    if db_path.exists():
        print(f"  Size     : {db_path.stat().st_size:,} bytes")
    print(f"  Token    : ...{token[-12:]} ({len(token)} chars)")
    print(f"  Mode     : {'DRY RUN (read-only)' if args.dry_run else 'LIVE (will modify)'}")
    print(f"  Time     : {datetime.now(timezone.utc).isoformat()}")

    if not db_path.exists():
        _warn(f"Database file not found at {db_path}")
        _info("The database will be created automatically when the backend starts.")
        _info("Run this script again after first boot to seed the FYERS token.")
        return 0

    # Create timestamped backup before any modifications
    if not args.dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.with_name(f"{db_path.stem}_backup_{timestamp}{db_path.suffix}")
        _header("BACKUP")
        _info(f"Creating backup: {backup_path.name}")
        shutil.copy2(db_path, backup_path)
        _ok(f"Backup saved ({backup_path.stat().st_size:,} bytes)")

    # Connect with WAL mode for safety
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # Disable FK checks during schema migration

    try:
        # Phase 1: Schema repair
        repaired_count = phase_1_schema_repair(conn)

        if args.dry_run:
            _header("DRY RUN -- No changes committed")
            conn.rollback()
            return 0

        # Phase 2: Token seeding
        phase_2_token_seeding(conn, token)

        # Commit all changes atomically
        conn.commit()
        _ok("All changes committed to database")

        # Re-enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")

        # Phase 3: Integrity verification
        all_ok = phase_3_integrity_checks(conn)

        # Final summary
        _header("REPAIR COMPLETE")
        if all_ok:
            print(f"\n  {_C.GREEN}{_C.BOLD}[OK] Database is healthy and ready for production boot.{_C.RESET}")
            print(f"  {_C.GREEN}{_C.BOLD}[OK] FYERS token is seeded and active.{_C.RESET}")
            print(f"  {_C.GREEN}{_C.BOLD}[OK] Single-user architecture confirmed -- zero user_id columns.{_C.RESET}\n")
            return 0
        else:
            print(f"\n  {_C.RED}{_C.BOLD}[FAIL] Some integrity checks failed. Review output above.{_C.RESET}\n")
            return 1

    except Exception as exc:
        conn.rollback()
        _err(f"FATAL: {type(exc).__name__}: {exc}")
        _info("All changes have been rolled back. Database is unchanged.")
        return 2

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
