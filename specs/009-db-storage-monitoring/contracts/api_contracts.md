# Interface Contracts: Sprint 4 – Database Storage + Basic Monitoring

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/spec.md)
**Created**: 2026-07-20

---

## 1. Python Library Interface (Token Persistence Runner)

We define a system-wide execution boundary in the application's service layers for generating and persisting Fyers access tokens:

```python
async def generate_and_persist_fyers_token(db: AsyncSession) -> dict[str, Any]:
    """
    Triggers the headless login flow, retrieves a new access token, 
    and handles its database persistence and monitoring updates.

    Args:
        db (AsyncSession): Active SQLAlchemy async database session.

    Returns:
        dict[str, Any]: Execution status reporting outcome:
            - Success: {"status": "Success", "saved_at": datetime, "token_preview": str}
            - Failure: {"status": "Failed", "error": str, "saved_at": datetime}

    Raises:
        # Re-raises the caught error after updating the database:
        FyersConfigError: Configuration missing.
        FyersAuthError: PIN/TOTP validation fails permanently.
        FyersConnectionError: Network timeout or Fyers server issues.
    """
```

### Call Guidance and Error Propagation
- When the runner executes `generate_fyers_access_token()`, it wraps the call in a `try...except` block.
- On success:
  - Writes the token to the database with `status = "Success"`, `last_error = None`.
  - Commits transaction.
- On exception:
  - Catches the exception, updates the database with `status = "Failed"`, `last_error = str(exception)`.
  - Commits transaction.
  - Re-raises the exception to ensure the orchestration system or background logs register the job failure.

---

## 2. CLI Interface / Automation Hook

The existing script [update_token.py](file:///D:/Work_Space/trading-system/update_token.py) is refactored from a hardcoded SQLite insertion utility to a dynamic Postgres-aware automation runner.

### Command Execution
```bash
python update_token.py
```

### Script Execution Logic
1. Reads environment settings (using Pydantic `settings` to load `DATABASE_URL`).
2. Instantiates an asynchronous session using `AsyncSessionLocal()`.
3. Invokes `generate_and_persist_fyers_token(db)`.
4. Outputs:
   - **Success (Exit Code 0)**: Prints `Token updated successfully.` and writes a masked preview of the saved token to standard output.
   - **Failure (Exit Code 1)**: Writes `Error: [Exception Class] - [Message]` to standard error and terminates.
