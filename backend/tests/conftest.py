from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generator
import logging
import re
import shutil
from datetime import datetime

import pytest


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "tests" / "artifacts" / "backend"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH = ARTIFACT_DIR / "test_app.db"

# Export artifact dir and RUN_ID early so the application picks them up when imported
RUN_ID = os.environ.get("RUN_ID") or datetime.utcnow().strftime("%Y%m%dT%H%M%S")
os.environ.setdefault("RUN_ID", RUN_ID)
os.environ.setdefault("TEST_ARTIFACT_DIR", str(ARTIFACT_DIR))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH.as_posix()}")
os.environ.setdefault("NIFTY500_SYMBOLS", "INFY-EQ,TCS-EQ,RELIANCE-EQ")
os.environ.setdefault("FYERS_ACCESS_TOKEN", "")


from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import get_db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import *  # noqa: F401,F403,E402


@pytest.fixture(autouse=True)
def test_settings() -> Generator[None, None, None]:
    settings.app_env = "test"
    settings.nifty500_symbols = ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]
    yield


@pytest.fixture()
def test_engine():
    engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, class_=Session)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def artifact_dir() -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


@pytest.fixture()
def write_artifact(artifact_dir: Path):
    def _write(name: str, payload: Any) -> Path:
        path = artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        return path

    return _write


@pytest.fixture(autouse=True)
def per_test_log(request, artifact_dir: Path):
    """Attach a per-test file handler so each test gets its own log file.

    Files are written to `tests/artifacts/backend/logs/<sanitized_test_name>.log`.
    """
    test_name = request.node.nodeid
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", test_name)
    path = artifact_dir / "logs" / f"{sanitized}.log"
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(path, encoding="utf-8", mode="w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        # Copy the sqlite DB file for offline inspection
        try:
            if TEST_DB_PATH.exists():
                dst = ARTIFACT_DIR / "db" / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', rep.nodeid)}.db"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(TEST_DB_PATH, dst)
        except Exception as e:
            try:
                (ARTIFACT_DIR / "db" / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', rep.nodeid)}_db_error.txt").write_text(str(e))
            except Exception:
                pass
