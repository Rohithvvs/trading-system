# PHASE F CLAIM VERIFICATION

## Claim
"Transactions write to SQLite while positions write to PostgreSQL"

## 1. Exact Transaction Insert Code
* **File:** `backend/app/services/paper_trading_service.py`
* **Line:** 239-249
* **Code Snippet:**
```python
                tx = PaperTransaction(
                    account_id=int(account.id),
                    timestamp=datetime.utcnow(),
                    symbol=filled_order.symbol,
                    action="BUY",
                    qty=int(filled_order.qty),
                    price=float(filled_order.filled_price) if filled_order.filled_price is not None else None,
                    amount=-float(filled_order.filled_price or 0.0) * int(filled_order.qty),
                    balance_after=float(account.cash_balance),
                )
                self.db.add(tx)
```
* **Runtime Database:** PostgreSQL

## 2. Exact Position Insert Code
* **File:** `backend/app/services/paper_trading_service.py`
* **Line:** 584-600
* **Code Snippet:**
```python
                position = PaperPosition(
                    account_id=account.id,
                    status="OPEN",
                    lifecycle_state="OPEN_POSITION",
                    symbol=order.symbol,
                    qty=order.qty,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    stop_loss=order.stop_loss,
                    target=order.target,
                    notes=order.notes,
                    source_signal=order.source_signal,
                    source_score=order.source_score,
                    source_confidence=order.source_confidence,
                )
                self.db.add(position)
                self.db.flush()
```
* **Runtime Database:** PostgreSQL

## 3. Exact SQLAlchemy Engine
* **File:** `backend/app/db/session.py`
* **Line:** 50-53, 65
* **Code Snippet:**
```python
sync_database_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
sync_connect_args = connect_args.copy()
sync_connect_args.pop("command_timeout", None)
sync_engine = create_engine(sync_database_url, connect_args=sync_connect_args, **pool_kwargs)
# ...
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine, expire_on_commit=False)
```

## 4. Exact Database URL
* **File:** `backend/app/config/settings.py`
* **Line:** 25
* **Code Snippet:**
```python
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
```

## 5. Exact Runtime Target Database
The runtime target database is **PostgreSQL**. Both `PaperTransaction` and `PaperPosition` instances are added to the exact same `self.db` (`SessionLocal`) session object. When `self.db.commit()` is executed on line 277 of `paper_trading_service.py`, both objects are written atomically to the PostgreSQL database bound to `sync_engine`.

The presence of the word "SQLite" in the source code comments (e.g., `# Log transaction (cash outflow) to SQLite`) and logger exception blocks (e.g., `Failed to write BUY transaction or notification to SQLite`) are purely stale text remnants from a prior state of the codebase. They do not dictate runtime behavior.

## Final Status
**UNVERIFIED**
