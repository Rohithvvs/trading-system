import pytest
import pandas as pd
import numpy as np
import sqlite3
from backend.app.services.candle_store import (
    store_candles, 
    load_candles, 
    init_db,
    DB_PATH
)
import os

@pytest.fixture(autouse=True)
def clean_candle_db():
    """Ensure a clean database per test"""
    # Delete the cache DB if it exists before and after each test
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass
            
    init_db()
    yield
    
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

def test_candle_deduplication():
    """Test that saving identical timestamps correctly deduplicates using INSERT OR REPLACE"""
    symbol = "NSE:TEST-EQ"
    
    # Save a first batch of candles
    df1 = pd.DataFrame([
        {"date": "2024-01-01", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
        {"date": "2024-01-02", "open": 105, "high": 115, "low": 100, "close": 112, "volume": 1500},
    ])
    store_candles(symbol, df1)
    
    # Save a second batch containing the exact same date (2024-01-02) but updated values
    df2 = pd.DataFrame([
        {"date": "2024-01-02", "open": 105, "high": 120, "low": 95, "close": 118, "volume": 2000}, # Updated!
        {"date": "2024-01-03", "open": 118, "high": 125, "low": 115, "close": 122, "volume": 1800},
    ])
    store_candles(symbol, df2)
    
    # Load and verify
    result_df = load_candles(symbol)
    
    # Ensure there are only 3 unique dates total
    assert len(result_df) == 3
    
    # Ensure the 2024-01-02 row was overwritten with df2's values
    jan2_row = result_df[result_df["date"] == "2024-01-02"].iloc[0]
    assert jan2_row["high"] == 120.0
    assert jan2_row["close"] == 118.0
    assert jan2_row["volume"] == 2000

def test_candle_nan_handling():
    """Test that NaNs are rejected or handled without crashing SQLite"""
    symbol = "NSE:NAN-EQ"
    
    # Pandas sometimes generates NaNs for missing data. 
    # SQLite float/real columns handle NULLs, but python floats might error.
    df = pd.DataFrame([
        {"date": "2024-01-01", "open": 100.0, "high": np.nan, "low": 90.0, "close": 105.0, "volume": 1000},
    ])
    
    # The float(np.nan) call in store_candles will succeed (becomes float('nan')), 
    # but SQLite doesn't natively support IEEE NaNs well without strict typing issues.
    # Our system expects float(row["high"]), which yields a python NaN.
    store_candles(symbol, df)
    
    result_df = load_candles(symbol)
    assert len(result_df) == 1
    # Check that high is NaN (using pd.isna)
    assert pd.isna(result_df.iloc[0]["high"])

def test_candle_data_integrity():
    """Verify that returned types correctly cast to floats/ints as defined in the DB"""
    symbol = "NSE:TYPE-EQ"
    
    df = pd.DataFrame([
        # Pass weird types that pandas might allow
        {"date": "2024-01-01", "open": "100.5", "high": 110, "low": 90.0, "close": 105, "volume": "1000"},
    ])
    
    store_candles(symbol, df)
    
    result_df = load_candles(symbol)
    
    # Validate types coming out of load_candles
    assert isinstance(result_df.iloc[0]["open"], float)
    assert result_df.iloc[0]["open"] == 100.5
    
    # Volume comes out as int/float depending on pandas fallback, but we should assert numeric
    assert pd.api.types.is_numeric_dtype(result_df["volume"])
    assert result_df.iloc[0]["volume"] == 1000
