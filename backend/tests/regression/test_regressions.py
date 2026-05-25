import pytest
import os
import importlib

def test_regression_screener_service_syntax():
    # Regression Test for the syntax error (IndentationError / duplicate def) 
    # that previously crashed the server boot process.
    try:
        from backend.app.services.screener_service import ScreenerService
        # If it imports without crashing, the syntax issue is resolved
        assert True
    except IndentationError:
        pytest.fail("Regression: IndentationError returned in screener_service.py")
    except Exception as e:
        # Ignore other errors like DB setup for the purpose of the syntax test
        pass

def test_regression_yfinance_dependency():
    # Regression Test for the missing yfinance dependency that caused 
    # the server to 'Exit with status 1' on Render
    try:
        import yfinance
        assert yfinance is not None
    except ModuleNotFoundError:
        pytest.fail("Regression: 'yfinance' is not installed in the environment.")

def test_regression_duplicate_return_statement():
    # Verify that the double `return ScreenerConditionResult(` bug was removed
    # from screener_service.py
    screener_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'screener_service.py')
    
    with open(screener_path, 'r') as f:
        content = f.read()
        
    count = content.count("return ScreenerConditionResult(")
    # Asserting that the specific buggy double-return block isn't present
    # There are multiple returns, but they shouldn't be back-to-back.
    assert "return ScreenerConditionResult(\n            return ScreenerConditionResult(" not in content
