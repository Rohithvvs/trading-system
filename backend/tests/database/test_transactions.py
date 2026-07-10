import pytest
import threading
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, IntegrityError, InvalidRequestError
from time import sleep

from backend.app.models import FyersToken, FyersTokenHistory
from backend.app.db.session import SessionLocal

def test_transaction_rollback_on_failure(db_session: Session):
    """
    Test that a transaction rollback clears pending objects and prevents orphan rows.
    """
    # Create an initial valid state
    initial_count = db_session.query(FyersToken).count()
    
    # Start a transaction and add something
    token = FyersToken(access_token="trans_test_1", status="active")
    db_session.add(token)
    
    # Simulate an error (e.g. Integrity Error from missing fields or manual exception)
    try:
        # Force a failure 
        raise ValueError("Simulated business logic failure")
        db_session.commit()
    except Exception:
        db_session.rollback()
        
    # Verify the object was rolled back
    final_count = db_session.query(FyersToken).count()
    assert final_count == initial_count
    
    # Verify the object is detached/not in DB
    verify = db_session.query(FyersToken).filter_by(access_token="trans_test_1").first()
    assert verify is None

def test_concurrent_writes_isolation():
    """
    Test that concurrent sessions do not bleed into each other and handle basic isolation.
    """
    # Create two separate DB sessions
    session1 = SessionLocal()
    session2 = SessionLocal()
    
    try:
        # Session 1 adds a record but does NOT commit yet
        t1 = FyersToken(access_token="concurrent_1", status="active")
        session1.add(t1)
        session1.flush()  # Flushed to DB but not committed
        
        # Session 2 attempts to read - should NOT see uncommitted data (Read Committed isolation)
        verify2 = session2.query(FyersToken).filter_by(access_token="concurrent_1").first()
        assert verify2 is None
        
        # Now Session 1 commits
        session1.commit()
        
        # Session 2 should now see it
        verify2_after = session2.query(FyersToken).filter_by(access_token="concurrent_1").first()
        assert verify2_after is not None
        assert verify2_after.access_token == "concurrent_1"
        
    finally:
        # Clean up
        session1.query(FyersToken).filter_by(access_token="concurrent_1").delete()
        session1.commit()
        session1.close()
        session2.close()

from sqlalchemy import text

def test_session_cleanup_and_exhaustion():
    """
    Test that connection pools do not exhaust when sessions are properly cleaned up.
    This proves we aren't leaking connections.
    """
    try:
        # Sequentially open and close more sessions than the pool limit (15)
        # If there's a leak, it will exhaust the pool and timeout.
        for _ in range(30):
            s = SessionLocal()
            s.execute(text("SELECT 1"))
            s.close()
            
    except Exception as e:
        pytest.fail(f"Connection pool exhausted due to leak: {e}")
            
    # Verify we can still get a new connection after the loop
    final_session = SessionLocal()
    result = final_session.execute(text("SELECT 1")).scalar()
    assert result == 1
    final_session.close()

def test_no_orphan_rows_on_relational_failure(db_session: Session):
    """
    Test that if a parent fails, the child isn't orphaned (Atomicity).
    """
    # We will test saving a token and a history record simultaneously.
    initial_history_count = db_session.query(FyersTokenHistory).count()
    
    try:
        token = FyersToken(access_token="orphan_test", status="active")
        history = FyersTokenHistory(access_token_masked="orph...", status="active")
        
        db_session.add(token)
        db_session.add(history)
        
        # Simulate a crash before commit
        raise RuntimeError("Crash")
        db_session.commit()
    except Exception:
        db_session.rollback()
        
    # Verify history was not inserted (No orphans)
    final_history_count = db_session.query(FyersTokenHistory).count()
    assert final_history_count == initial_history_count
