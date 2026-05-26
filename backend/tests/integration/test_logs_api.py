from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.models.system_log import SystemLog
from backend.app.services.logger_service import logger_service


@app.get("/api/test/logs-zero-division")
def logs_zero_division_test():
    return {"value": 1 / 0}


def test_logs_api_filters_by_level_and_symbol(client: TestClient, db_session: Session):
    levels = ["INFO", "ERROR", "CRITICAL", "ERROR", "INFO", "WARN", "ERROR", "DEBUG", "CRITICAL", "INFO"]
    symbols = [
        "INFY-EQ",
        "HINDALCO-EQ",
        "HINDALCO-EQ",
        "SBIN-EQ",
        "TCS-EQ",
        "HINDALCO-EQ",
        "HINDALCO-EQ",
        "INFY-EQ",
        "RELIANCE-EQ",
        "HINDALCO-EQ",
    ]
    for index, (level, symbol) in enumerate(zip(levels, symbols)):
        db_session.add(
            SystemLog(
                timestamp=datetime.utcnow() - timedelta(seconds=index),
                level=level,
                source="API",
                module="filter_seed",
                endpoint="/seed",
                message=f"{level} {symbol} {index}",
                symbol=symbol,
                environment="TEST",
            )
        )
    db_session.commit()

    response = client.get("/api/logs?level=ERROR&symbol=HINDALCO-EQ")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {row["level"] for row in rows} == {"ERROR"}
    assert {row["symbol"] for row in rows} == {"HINDALCO-EQ"}
    assert all(row["module"] == "filter_seed" for row in rows)


def test_global_exception_handler_persists_zero_division_traceback(client: TestClient, db_session: Session):
    response = client.get("/api/test/logs-zero-division", headers={"X-Correlation-ID": "cid-zero-div"})

    assert response.status_code == 500
    assert response.json()["detail"] == "An unexpected system error occurred. This has been logged for our engineers."

    log = (
        db_session.query(SystemLog)
        .filter(SystemLog.level == "ERROR", SystemLog.correlationId == "cid-zero-div")
        .order_by(SystemLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.module == "global_exception_handler"
    assert log.endpoint == "GET /api/test/logs-zero-division"
    assert "division by zero" in log.message
    assert "ZeroDivisionError" in log.traceback
    assert log.error_hash


def test_logs_websocket_receives_realtime_broadcast(client: TestClient):
    with client.websocket_connect("/api/logs/stream") as websocket:
        logger_service.log(
            level="CRITICAL",
            source="SYSTEM",
            module="ws_broadcast",
            message="streamed circuit breaker event",
            structured_data={"symbol": "HINDALCO-EQ"},
        )

        payload = websocket.receive_json()

    assert payload["level"] == "CRITICAL"
    assert payload["source"] == "SYSTEM"
    assert payload["module"] == "ws_broadcast"
    assert payload["message"] == "streamed circuit breaker event"
    assert payload["structured_data"]["symbol"] == "HINDALCO-EQ"
    assert "emergency_snapshot" in payload["structured_data"]
