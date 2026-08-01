"""Integration tests for scan completion active pre-warming.

Maps to User Story 2, FR-005.

Pre-warm split:
- ``save_latest_scan`` writes ``analysis:scan:latest:v1`` (scan_store schema + available).
- ``LatestScanService.prewarm_scanner_latest_cache`` writes ``scanner:latest:v1``
  (dashboard / LatestScanService schema) after persist commit.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.db.scan_store import save_latest_scan
from app.services.latest_scan_service import LatestScanService


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.set_calls: List[tuple] = []

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
        if nx and key in self.store:
            return False
        self.set_calls.append((key, value, ex))
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        for k in keys:
            self.store.pop(k, None)
        return len(keys)


@pytest.mark.asyncio
async def test_save_latest_scan_triggers_prewarm(monkeypatch):
    """US2: save_latest_scan completes without error when pre-warming is enabled."""
    set_scanner_cache_enabled(monkeypatch, True)
    test_payload = {
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "buy_candidates": [{"symbol": "INFY", "score": 88.0}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    await save_latest_scan(test_payload)


@pytest.mark.asyncio
async def test_prewarm_uses_orjson_not_missing_json_import():
    """C1 regression: pre-warm path must not reference undefined json module."""
    import re

    import app.db.scan_store as scan_store_module

    source = open(scan_store_module.__file__, encoding="utf-8").read()
    assert "orjson.dumps" in source
    # Must not call bare json.dumps (NameError if json is not imported).
    # Note: substring "json.dumps" also appears inside "orjson.dumps".
    assert re.search(r"(?<![A-Za-z0-9_])json\.dumps\b", source) is None
    assert "import json" not in source


@pytest.mark.asyncio
async def test_prewarm_sets_analysis_cache_key(monkeypatch):
    """US2 / FR-005: On save_latest_scan, analysis:scan:latest:v1 is actively SET."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(settings, "scanner_latest_cache_ttl_seconds", 300)

    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    test_payload = {
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "buy_candidates": [{"symbol": "INFY", "score": 88.0}],
        "watch_candidates": [],
        "rejected_candidates": [],
        "shortlisted_symbols": ["INFY"],
        "buy_candidate_symbols": ["INFY"],
        "watch_candidate_symbols": [],
    }

    await save_latest_scan(test_payload)

    keys_set = {call[0] for call in redis_mock.set_calls}
    assert "analysis:scan:latest:v1" in keys_set
    assert "analysis:scan:latest:v1" in redis_mock.store
    # Dashboard key must NOT be filled with scan_store JSONB (wrong schema).
    assert "scanner:latest:v1" not in keys_set

    analysis = json.loads(redis_mock.store["analysis:scan:latest:v1"])
    assert analysis.get("available") is True


@pytest.mark.asyncio
async def test_prewarm_skipped_when_flag_disabled(monkeypatch):
    """US2 + US4: Flag OFF must not write Redis during scan save."""
    set_scanner_cache_enabled(monkeypatch, False)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    test_payload = {
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "buy_candidates": [{"symbol": "INFY", "score": 88.0}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    await save_latest_scan(test_payload)
    assert redis_mock.set_calls == []


@pytest.mark.asyncio
async def test_prewarm_failure_does_not_break_save(monkeypatch):
    """Pre-warm Redis errors must not fail the scan persist path."""
    set_scanner_cache_enabled(monkeypatch, True)
    class BoomRedis:
        async def set(self, key, value, ex=None):
            raise ConnectionError("prewarm boom")

        async def get(self, key):
            return None

        async def delete(self, *keys):
            return 0

    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: BoomRedis(),
    )

    test_payload = {
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "buy_candidates": [{"symbol": "TCS", "score": 70.0}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    await save_latest_scan(test_payload)


@pytest.mark.asyncio
async def test_prewarm_overwrites_stale_analysis_cache(monkeypatch):
    """US2 AC1: Active SET overwrites previously cached stale analysis key."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    redis_mock.store["analysis:scan:latest:v1"] = json.dumps(
        {"available": True, "old": True}
    )
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    new_payload = {
        "scan_timestamp": "NEW_TS",
        "buy_candidates": [{"symbol": "WIPRO", "score": 60.0}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }
    await save_latest_scan(new_payload)

    analysis_cached = redis_mock.store["analysis:scan:latest:v1"]
    assert "NEW_TS" in analysis_cached or "WIPRO" in analysis_cached
    assert "old" not in analysis_cached or "NEW_TS" in analysis_cached


@pytest.mark.asyncio
async def test_scanner_prewarm_writes_dashboard_schema(monkeypatch):
    """C2: scanner:latest:v1 pre-warm uses LatestScanService dashboard payload."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    dashboard_payload = {
        "scan_id": "scan-123",
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "last_scan_completed_at": "2026-07-27T09:45:00Z",
        "total_scanned": 10,
        "valid_symbols": 10,
        "buy_count": 1,
        "watch_count": 0,
        "rejected_count": 0,
        "buy_candidates": [
            {
                "symbol": "RELIANCE",
                "recommendation": "BUY",
                "score": 85.5,
                "close_price": 100.0,
                "sma50": None,
                "sma200": None,
                "rsi": 60.0,
                "macd": None,
                "volume": None,
                "reason": "test",
            }
        ],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    service = LatestScanService(db=AsyncMock())
    service.get_latest_completed_scan = AsyncMock(return_value=dashboard_payload)

    await service.prewarm_scanner_latest_cache()

    assert "scanner:latest:v1" in redis_mock.store
    cached = json.loads(redis_mock.store["scanner:latest:v1"])
    assert cached["scan_id"] == "scan-123"
    assert cached["buy_candidates"][0]["symbol"] == "RELIANCE"
    assert "recommendation" in cached["buy_candidates"][0]


@pytest.mark.asyncio
async def test_scanner_prewarm_skipped_when_flag_disabled(monkeypatch):
    set_scanner_cache_enabled(monkeypatch, False)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    service = LatestScanService(db=AsyncMock())
    service.get_latest_completed_scan = AsyncMock(
        return_value={"scan_id": "x", "buy_candidates": []}
    )
    await service.prewarm_scanner_latest_cache()
    assert redis_mock.set_calls == []
    service.get_latest_completed_scan.assert_not_awaited()
