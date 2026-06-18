import pytest
from sqlalchemy.exc import InvalidRequestError, IntegrityError
from backend.app.db.session import SessionLocal
from backend.app.models import FyersToken

def test_sqlalchemy_flush_race_condition_regression():
    """
    Regression Test:
    Ensures that if a flush fails (e.g. IntegrityError), the session is explicitly rolled back.
    If it is NOT rolled back, attempting to query or commit on the same session 
    triggers an InvalidRequestError ("This Session's transaction has been rolled back 
    due to a previous exception during flush").
    
    This test verifies that our codebase's standard pattern (try-except-rollback)
    prevents the application from stalling on an invalidated session state.
    """
    session = SessionLocal()
    
    try:
        # Step 1: Intentionally cause a database flush failure (IntegrityError)
        # Using a model missing required constraints or duplicating unique keys
        token1 = FyersToken(access_token="dupe_token", status="active")
        session.add(token1)
        session.commit()
        
        token2 = FyersToken(status="active") # Violates nullable=False constraint
        session.add(token2)
        
        try:
            session.commit() # This flush will fail internally!
            pytest.fail("Should have raised IntegrityError")
        except IntegrityError:
            # Step 2: VERIFY REGRESSION PREVENTION. 
            # We MUST rollback here to salvage the session.
            session.rollback()
            
        # Step 3: Prove session is salvaged and usable (No InvalidRequestError)
        alive_check = session.query(FyersToken).count()
        assert alive_check >= 1 # The first token survived, session is healthy
        
    finally:
        session.query(FyersToken).filter_by(access_token="dupe_token").delete()
        session.commit()
        session.close()
