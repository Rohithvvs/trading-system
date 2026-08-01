"""Regression: global exception handler masks secrets and persists structured logs."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Import the same app instance used by conftest's client fixture (avoid dual-import split).
try:
    from app.main import app
    from app.models.system_log import SystemLog
    from app.services.logger_service import logger_service
except ModuleNotFoundError:  # pragma: no cover
    from backend.app.main import app
    from backend.app.models.system_log import SystemLog
    from backend.app.services.logger_service import logger_service

_TEST_PATH = "/api/test/global-exception-logging"


def _ensure_test_route() -> None:
    """Register the intentional failure route on the live app instance once."""
    for route in app.routes:
        if getattr(route, "path", None) == _TEST_PATH:
            return

    @app.get(_TEST_PATH)
    def global_exception_logging_test():
        raise RuntimeError("broker failed password=supersecret access_token=tok_123")


def test_global_exception_handler_masks_data_and_writes_log(db_session: Session):
    _ensure_test_route()

    # raise_server_exceptions=False: Starlette BaseHTTPMiddleware can re-surface the
    # original exception to TestClient even after the app exception handler returns 500.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(_TEST_PATH, headers={"X-Correlation-ID": "cid-test-500"})

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

    assert logs, "Expected an ERROR SystemLog row from global_exception_handler"
    log = logs[0]
    assert log.module == "global_exception_handler"
    assert log.endpoint == f"GET {_TEST_PATH}"
    assert log.correlationId == "cid-test-500"
    assert log.error_hash
    assert "***MASKED***" in (log.message or "")
    assert "supersecret" not in (log.message or "")
    assert "tok_123" not in (log.message or "")
    assert log.traceback
    assert "supersecret" not in (log.traceback or "")
    assert "tok_123" not in (log.traceback or "")


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
