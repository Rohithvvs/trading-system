from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.models.system_log import SystemLog
from backend.app.services.logger_service import logger_service


@app.get("/api/test/global-exception-logging")
def global_exception_logging_test():
    raise RuntimeError("broker failed password=supersecret access_token=tok_123")


def test_global_exception_handler_masks_data_and_writes_log(client: TestClient, db_session: Session):
    response = client.get("/api/test/global-exception-logging", headers={"X-Correlation-ID": "cid-test-500"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected system error occurred. This has been logged for our engineers."
    }

    logs = (
        db_session.query(SystemLog)
        .filter(SystemLog.level == "ERROR")
        .order_by(SystemLog.id.desc())
        .all()
    )

    assert logs
    log = logs[0]
    assert log.module == "global_exception_handler"
    assert log.endpoint == "GET /api/test/global-exception-logging"
    assert log.correlationId == "cid-test-500"
    assert log.error_hash
    assert "***MASKED***" in log.message
    assert "supersecret" not in log.message
    assert "tok_123" not in log.message
    assert log.traceback
    assert "supersecret" not in log.traceback
    assert "tok_123" not in log.traceback


def test_logger_masks_structured_data_before_persist(db_session: Session):
    logger_service.log(
        level="ERROR",
        source="API",
        module="masking_test",
        message="failed for client_secret=abc123",
        structured_data={
            "access_token": "plain-token",
            "nested": {"pin": "4321", "note": "auth_code=xyz"},
        },
    )

    import anyio

    anyio.run(logger_service.flush_now)
    log = db_session.query(SystemLog).filter(SystemLog.module == "masking_test").one()

    assert log.message == "failed for client_secret=***MASKED***"
    assert log.structured_data["access_token"] == "***MASKED***"
    assert log.structured_data["nested"]["pin"] == "***MASKED***"
    assert log.structured_data["nested"]["note"] == "auth_code=***MASKED***"
