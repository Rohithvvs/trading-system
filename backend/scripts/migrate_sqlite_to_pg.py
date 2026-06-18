"""
SQLite to PostgreSQL Data Migration Script
"""
import asyncio
import argparse
import hashlib
import json
import socket
import sys
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import aiosqlite
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to path for importing app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.paper_trading import PaperTradingAccount

MIGRATION_LOCK_ID = 999999

def cast_decimal(value: float | None, precision: int) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(f"1e-{precision}"))

def localize_utc(naive_dt_str: str | None) -> datetime | None:
    if naive_dt_str is None:
        return None
    try:
        dt = datetime.fromisoformat(naive_dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None

def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

async def verify_live_write_freeze():
    # A robust check would query the OS process list or lock files.
    # For now, we assume if we can get the migration lock, we are good,
    # but we should also check if uvicorn is bound to port 8000.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    if result == 0:
        raise RuntimeError("Uvicorn is running on port 8000! Aborting migration to ensure SQLite is frozen.")

async def run_migration(sqlite_path: Path, dry_run: bool, chunk_size: int, target_table: str | None):
    manifest: Dict[str, Any] = {
        "migration_run_id": str(uuid.uuid4()),
        "start_timestamp": datetime.utcnow().isoformat(),
        "dry_run": dry_run,
        "chunk_size": chunk_size,
        "operator": socket.gethostname(),
        "status": "STARTED"
    }

    try:
        await verify_live_write_freeze()
    except Exception as e:
        manifest["status"] = "FAILED"
        manifest["error"] = str(e)
        write_manifest(manifest)
        print(f"FAILED: {e}")
        return

    # 1. Hashing and Snapshot Validation
    print(f"Hashing SQLite file: {sqlite_path}...")
    try:
        start_hash = hash_file(sqlite_path)
        manifest["source_sqlite_hash"] = start_hash
    except FileNotFoundError:
        print(f"SQLite file not found at {sqlite_path}")
        return

    # 2. Acquire PG Lock and Connect
    async with AsyncSessionLocal() as pg_session:
        # Advisory lock
        lock_result = await pg_session.execute(text(f"SELECT pg_try_advisory_lock({MIGRATION_LOCK_ID})"))
        if not lock_result.scalar():
            print("FAILED: Could not acquire PostgreSQL advisory lock. Is another migration running?")
            return
        
        try:
            # 3. Connect to SQLite (Immutable Read-Only)
            sqlite_uri = f"file:{sqlite_path}?mode=ro"
            async with aiosqlite.connect(sqlite_uri, uri=True) as sqlite_conn:
                sqlite_conn.row_factory = aiosqlite.Row
                print(f"Connected to SQLite {sqlite_path} (READ-ONLY)")
                
                run_id = manifest["migration_run_id"]
                if target_table in (None, "paper_trading_accounts"):
                    await migrate_accounts(sqlite_conn, pg_session, chunk_size, dry_run, run_id)
                if target_table in (None, "paper_trading_orders"):
                    await migrate_orders(sqlite_conn, pg_session, chunk_size, dry_run, run_id)
                if target_table in (None, "paper_trading_positions"):
                    await migrate_positions(sqlite_conn, pg_session, chunk_size, dry_run, run_id)
                if target_table in (None, "paper_trading_transactions"):
                    await migrate_transactions(sqlite_conn, pg_session, chunk_size, dry_run, run_id)
                if target_table in (None, "paper_trading_trade_history"):
                    await migrate_trade_history(sqlite_conn, pg_session, chunk_size, dry_run, run_id)
                
                if not dry_run and target_table is None:
                    print("Running post-migration Sequence Reseeding and FK Validation...")
                    await run_post_migration_validation(pg_session)
                
                # 4. Final Hashing to ensure immutability
                end_hash = hash_file(sqlite_path)
                if start_hash != end_hash:
                    raise RuntimeError("FATAL: SQLite file was modified during migration!")
                
                manifest["status"] = "SUCCESS"
        except Exception as e:
            manifest["status"] = "FAILED"
            manifest["error"] = str(e)
            print(f"Migration Failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Release lock
            await pg_session.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
            await pg_session.commit()
            
    manifest["finish_timestamp"] = datetime.utcnow().isoformat()
    write_manifest(manifest)
    print("Migration finished. Manifest written.")

async def run_post_migration_validation(pg_session: AsyncSession):
    tables = [
        "paper_trading_accounts",
        "paper_trading_orders",
        "paper_trading_positions",
        "paper_trading_transactions",
        "paper_trading_trade_history"
    ]
    
    # Reseed sequences
    for tbl in tables:
        query = text(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE(MAX(id), 1)) FROM {tbl};")
        await pg_session.execute(query)
    
    await pg_session.commit()
    print("Sequences reseeded successfully.")
    
    # FK Validation
    fk_queries = {
        "orders_orphans": "SELECT COUNT(*) FROM paper_trading_orders WHERE account_id NOT IN (SELECT id FROM paper_trading_accounts)",
        "positions_orphans": "SELECT COUNT(*) FROM paper_trading_positions WHERE account_id NOT IN (SELECT id FROM paper_trading_accounts)",
        "transactions_orphans": "SELECT COUNT(*) FROM paper_trading_transactions WHERE account_id NOT IN (SELECT id FROM paper_trading_accounts)",
        "history_orphans": "SELECT COUNT(*) FROM paper_trading_trade_history WHERE account_id NOT IN (SELECT id FROM paper_trading_accounts)"
    }
    
    for name, q in fk_queries.items():
        res = await pg_session.execute(text(q))
        count = res.scalar()
        if count and count > 0:
            raise RuntimeError(f"FK Validation Failed! {name} has {count} orphaned rows!")
    print("Foreign Key validation passed successfully.")

async def get_checkpoint(pg_session: AsyncSession, table_name: str) -> dict:
    query = text("SELECT last_processed_primary_key, last_processed_chunk FROM migration_checkpoints WHERE table_name = :t")
    res = await pg_session.execute(query, {"t": table_name})
    row = res.fetchone()
    if row:
        return {"last_pk": row[0], "last_chunk": row[1]}
    return {"last_pk": 0, "last_chunk": 0}

async def update_checkpoint(pg_session: AsyncSession, table_name: str, last_pk: int, last_chunk: int, rows_in_chunk: int, run_id: str):
    query = text("""
        INSERT INTO migration_checkpoints 
        (table_name, last_processed_primary_key, last_processed_chunk, rows_migrated, started_at, updated_at, migration_status, migration_run_id)
        VALUES (:t, :pk, :c, :r, :now, :now, 'MIGRATING', :run_id)
        ON CONFLICT (table_name) DO UPDATE SET 
        last_processed_primary_key = EXCLUDED.last_processed_primary_key,
        last_processed_chunk = EXCLUDED.last_processed_chunk,
        rows_migrated = migration_checkpoints.rows_migrated + EXCLUDED.rows_migrated,
        updated_at = EXCLUDED.updated_at,
        migration_status = EXCLUDED.migration_status,
        migration_run_id = EXCLUDED.migration_run_id
    """)
    await pg_session.execute(query, {
        "t": table_name,
        "pk": last_pk,
        "c": last_chunk,
        "r": rows_in_chunk,
        "now": datetime.utcnow(),
        "run_id": run_id
    })

async def migrate_accounts(sqlite_conn: aiosqlite.Connection, pg_session: AsyncSession, chunk_size: int, dry_run: bool, run_id: str):
    print("Migrating paper_trading_accounts...")
    ckpt = await get_checkpoint(pg_session, "paper_trading_accounts")
    last_pk = ckpt["last_pk"]
    chunk_idx = ckpt["last_chunk"]

    async with sqlite_conn.execute(f"SELECT * FROM paper_trading_accounts WHERE id > {last_pk} ORDER BY id ASC") as cursor:
        while True:
            rows = await cursor.fetchmany(chunk_size)
            if not rows:
                break
                
            chunk_idx += 1
            max_id = last_pk
            for row in rows:
                acct = PaperTradingAccount(
                    id=row['id'],
                    name=row['name'],
                    base_currency=row['base_currency'],
                    starting_balance=cast_decimal(row['starting_balance'], 2),
                    cash_balance=cast_decimal(row['cash_balance'], 2),
                    max_risk_per_trade=cast_decimal(row['max_risk_per_trade'], 8),
                    created_at=localize_utc(row['created_at']),
                    updated_at=localize_utc(row['updated_at'])
                )
                pg_session.add(acct)
                if row['id'] > max_id:
                    max_id = row['id']
            
            if not dry_run:
                await update_checkpoint(pg_session, "paper_trading_accounts", max_id, chunk_idx, len(rows), run_id)
            
            if dry_run:
                await pg_session.rollback()
                print(f"DRY RUN: Processed chunk of {len(rows)} accounts. Rolled back.")
            else:
                await pg_session.commit()
                print(f"LIVE: Committed chunk {chunk_idx} of {len(rows)} accounts (Up to ID: {max_id}).")

from backend.app.models.paper_trading import PaperOrder, PaperPosition, PaperTransaction, PaperTradeHistory

def get_row(row, key, default=None):
    try:
        val = row[key]
        return val if val is not None else default
    except IndexError:
        return default

async def migrate_orders(sqlite_conn: aiosqlite.Connection, pg_session: AsyncSession, chunk_size: int, dry_run: bool, run_id: str):
    print("Migrating paper_trading_orders...")
    ckpt = await get_checkpoint(pg_session, "paper_trading_orders")
    last_pk = ckpt["last_pk"]
    chunk_idx = ckpt["last_chunk"]

    async with sqlite_conn.execute(f"SELECT * FROM paper_trading_orders WHERE id > {last_pk} ORDER BY id ASC") as cursor:
        while True:
            rows = await cursor.fetchmany(chunk_size)
            if not rows:
                break
            
            chunk_idx += 1
            max_id = last_pk
            for row in rows:
                order = PaperOrder(
                    id=row['id'],
                    account_id=row['account_id'],
                    symbol=row['symbol'],
                    side=row['side'],
                    order_type=row['order_type'],
                    lifecycle_state=get_row(row, 'lifecycle_state', 'PENDING_ENTRY'),
                    product_type=get_row(row, 'product_type', 'CNC'),
                    qty=cast_decimal(row['qty'], 8),
                    order_price=cast_decimal(row['order_price'], 8),
                    stop_price=cast_decimal(get_row(row, 'stop_price'), 8),
                    stop_loss=cast_decimal(row['stop_loss'], 8),
                    target=cast_decimal(row['target'], 8),
                    status=row['status'],
                    requested_entry_price=cast_decimal(get_row(row, 'requested_entry_price'), 8),
                    monitor_enabled=bool(get_row(row, 'monitor_enabled', True)),
                    paused_reason=get_row(row, 'paused_reason'),
                    last_evaluated_at=localize_utc(get_row(row, 'last_evaluated_at')),
                    last_seen_ltp=cast_decimal(get_row(row, 'last_seen_ltp'), 8),
                    notes=row['notes'],
                    source_signal=row['source_signal'],
                    source_score=cast_decimal(row['source_score'], 8),
                    source_confidence=cast_decimal(row['source_confidence'], 8),
                    filled_price=cast_decimal(row['filled_price'], 8),
                    idempotency_key=get_row(row, 'idempotency_key') or f"migrated:order:{row['id']}",
                    created_at=localize_utc(row['created_at']),
                    updated_at=localize_utc(get_row(row, 'updated_at')) or localize_utc(row['created_at']),
                    filled_at=localize_utc(row['filled_at']),
                    cancelled_at=localize_utc(row['cancelled_at'])
                )
                pg_session.add(order)
                if row['id'] > max_id:
                    max_id = row['id']
            
            if not dry_run:
                await update_checkpoint(pg_session, "paper_trading_orders", max_id, chunk_idx, len(rows), run_id)
            
            if dry_run:
                await pg_session.rollback()
                print(f"DRY RUN: Processed chunk of {len(rows)} orders. Rolled back.")
            else:
                await pg_session.commit()
                print(f"LIVE: Committed chunk {chunk_idx} of {len(rows)} orders (Up to ID: {max_id}).")

async def migrate_positions(sqlite_conn: aiosqlite.Connection, pg_session: AsyncSession, chunk_size: int, dry_run: bool, run_id: str):
    print("Migrating paper_trading_positions...")
    ckpt = await get_checkpoint(pg_session, "paper_trading_positions")
    last_pk = ckpt["last_pk"]
    chunk_idx = ckpt["last_chunk"]

    async with sqlite_conn.execute(f"SELECT * FROM paper_trading_positions WHERE id > {last_pk} ORDER BY id ASC") as cursor:
        while True:
            rows = await cursor.fetchmany(chunk_size)
            if not rows:
                break
            
            chunk_idx += 1
            max_id = last_pk
            for row in rows:
                pos = PaperPosition(
                    id=row['id'],
                    account_id=row['account_id'],
                    status=get_row(row, 'status', 'OPEN'),
                    lifecycle_state=get_row(row, 'lifecycle_state', 'OPEN_POSITION'),
                    symbol=row['symbol'],
                    qty=cast_decimal(row['qty'], 8),
                    avg_entry_price=cast_decimal(row['avg_entry_price'], 8),
                    current_price=cast_decimal(row['current_price'], 8),
                    realized_pnl=cast_decimal(get_row(row, 'realized_pnl') or 0.0, 2),
                    unrealized_pnl=cast_decimal(get_row(row, 'unrealized_pnl') or 0.0, 2),
                    stop_loss=cast_decimal(row['stop_loss'], 8),
                    target=cast_decimal(row['target'], 8),
                    monitor_enabled=bool(get_row(row, 'monitor_enabled', True)),
                    paused_reason=get_row(row, 'paused_reason'),
                    notes=row['notes'],
                    source_signal=row['source_signal'],
                    source_score=cast_decimal(row['source_score'], 8),
                    source_confidence=cast_decimal(row['source_confidence'], 8),
                    created_at=localize_utc(row['created_at']),
                    updated_at=localize_utc(row['updated_at'])
                )
                pg_session.add(pos)
                if row['id'] > max_id:
                    max_id = row['id']
                
            if not dry_run:
                await update_checkpoint(pg_session, "paper_trading_positions", max_id, chunk_idx, len(rows), run_id)
                
            if dry_run:
                await pg_session.rollback()
                print(f"DRY RUN: Processed chunk of {len(rows)} positions. Rolled back.")
            else:
                await pg_session.commit()
                print(f"LIVE: Committed chunk {chunk_idx} of {len(rows)} positions (Up to ID: {max_id}).")

async def migrate_transactions(sqlite_conn: aiosqlite.Connection, pg_session: AsyncSession, chunk_size: int, dry_run: bool, run_id: str):
    print("Migrating paper_trading_transactions...")
    ckpt = await get_checkpoint(pg_session, "paper_trading_transactions")
    last_pk = ckpt["last_pk"]
    chunk_idx = ckpt["last_chunk"]

    async with sqlite_conn.execute(f"SELECT * FROM paper_trading_transactions WHERE id > {last_pk} ORDER BY id ASC") as cursor:
        while True:
            rows = await cursor.fetchmany(chunk_size)
            if not rows:
                break
            
            chunk_idx += 1
            max_id = last_pk
            for row in rows:
                tx = PaperTransaction(
                    id=row['id'],
                    account_id=row['account_id'],
                    timestamp=localize_utc(row['timestamp']),
                    symbol=row['symbol'],
                    action=row['action'],
                    qty=row['qty'],
                    price=row['price'],
                    amount=row['amount'],
                    balance_after=row['balance_after']
                )
                pg_session.add(tx)
                if row['id'] > max_id:
                    max_id = row['id']
                
            if not dry_run:
                await update_checkpoint(pg_session, "paper_trading_transactions", max_id, chunk_idx, len(rows), run_id)
                
            if dry_run:
                await pg_session.rollback()
                print(f"DRY RUN: Processed chunk of {len(rows)} transactions. Rolled back.")
            else:
                await pg_session.commit()
                print(f"LIVE: Committed chunk {chunk_idx} of {len(rows)} transactions (Up to ID: {max_id}).")

async def migrate_trade_history(sqlite_conn: aiosqlite.Connection, pg_session: AsyncSession, chunk_size: int, dry_run: bool, run_id: str):
    print("Migrating paper_trading_trade_history...")
    ckpt = await get_checkpoint(pg_session, "paper_trading_trade_history")
    last_pk = ckpt["last_pk"]
    chunk_idx = ckpt["last_chunk"]

    async with sqlite_conn.execute(f"SELECT * FROM paper_trading_trade_history WHERE id > {last_pk} ORDER BY id ASC") as cursor:
        while True:
            rows = await cursor.fetchmany(chunk_size)
            if not rows:
                break
            
            chunk_idx += 1
            max_id = last_pk
            for row in rows:
                th = PaperTradeHistory(
                    id=row['id'],
                    account_id=row['account_id'],
                    symbol=row['symbol'],
                    qty=cast_decimal(row['qty'], 8),
                    entry_price=cast_decimal(row['entry_price'], 8),
                    exit_price=cast_decimal(row['exit_price'], 8),
                    pnl=cast_decimal(row['pnl'], 2),
                    pnl_percent=cast_decimal(row['pnl_percent'], 2),
                    notes=row['notes'],
                    source_signal=row['source_signal'],
                    source_score=cast_decimal(row['source_score'], 8),
                    source_confidence=cast_decimal(row['source_confidence'], 8),
                    opened_at=localize_utc(row['opened_at']),
                    closed_at=localize_utc(row['closed_at']),
                    exit_reason=get_row(row, 'exit_reason'),
                    created_at=localize_utc(get_row(row, 'created_at')) or localize_utc(row['opened_at']),
                    updated_at=localize_utc(get_row(row, 'updated_at')) or localize_utc(row['closed_at'])
                )
                pg_session.add(th)
                if row['id'] > max_id:
                    max_id = row['id']
                
            if not dry_run:
                await update_checkpoint(pg_session, "paper_trading_trade_history", max_id, chunk_idx, len(rows), run_id)
                
            if dry_run:
                await pg_session.rollback()
                print(f"DRY RUN: Processed chunk of {len(rows)} trade history records. Rolled back.")
            else:
                await pg_session.commit()
                print(f"LIVE: Committed chunk {chunk_idx} of {len(rows)} trade history records (Up to ID: {max_id}).")

def write_manifest(manifest: dict):
    with open("migration_run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", type=str, default="trading_system.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--table", type=str, default=None)
    
    args = parser.parse_args()
    sqlite_path = Path(args.sqlite_path).resolve()
    
    asyncio.run(run_migration(sqlite_path, args.dry_run, args.chunk_size, args.table))

