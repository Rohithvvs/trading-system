import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.system_log import SystemLog
from backend.app.main import app

def test_api_logs_get_and_delete(client: TestClient, db_session: Session):
    # Ensure empty start
    client.delete("/api/logs?days_old=0")

    # Seed DB with explicit dates
    log1 = SystemLog(
        level="ERROR", 
        module="test_module", 
        message="error_msg", 
        endpoint="/test_err", 
        timestamp=datetime.utcnow() - timedelta(days=10)
    )
    log2 = SystemLog(
        level="INFO", 
        module="test_module", 
        message="info_msg", 
        endpoint="/test_info", 
        timestamp=datetime.utcnow() - timedelta(days=2)
    )
    db_session.add(log1)
    db_session.add(log2)
    db_session.commit()

    # Test GET
    res = client.get("/api/logs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2

    # Test GET with level filter
    res = client.get("/api/logs?level=ERROR")
    data = res.json()
    assert len(data) >= 1
    assert data[0]["message"] == "error_msg"

    # Test DELETE old logs (days_old=7)
    res = client.delete("/api/logs?days_old=7")
    assert res.status_code == 200
    
    # Verify only log2 remains
    res = client.get("/api/logs")
    data = res.json()
    assert any(d["message"] == "info_msg" for d in data)
    assert not any(d["message"] == "error_msg" for d in data)

    # Test DELETE all (days_old=0)
    res = client.delete("/api/logs?days_old=0")
    assert res.status_code == 200
    
    res = client.get("/api/logs")
    # There should only be 1 log left (the DELETE command we just ran!)
    data = res.json()
    assert len(data) == 1
    assert "DELETE /api/logs" in data[0]["message"]

def test_exception_handler_and_middleware(client: TestClient, db_session: Session):
    client.delete("/api/logs?days_old=0")
    
    @app.get("/api/crash_test")
    def crash_test():
        raise ValueError("Simulated crash")
    
    res = client.get("/api/crash_test")
    assert res.status_code == 500
    assert res.json()["detail"] == "An unexpected system error occurred. This has been logged for our engineers."

    res = client.get("/api/logs?level=ERROR")
    data = res.json()
    assert len(data) >= 1
    assert data[0]["module"] == "http_middleware_exception"
    assert "Simulated crash" in data[0]["message"]
    assert "Traceback" in data[0]["traceback"]

    # Test HTTP middleware logs POST
    res = client.post("/api/logs", json={"some": "data"}) # 405 Method Not Allowed, but still logs
    
    res = client.get("/api/logs?level=INFO")
    data = res.json()
    assert len(data) > 0
    assert any("POST /api/logs" in d["message"] for d in data)
