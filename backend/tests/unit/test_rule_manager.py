"""Unit tests for FEAT-012 RuleManager (Minimal Promotion Gate & Kill-Switch).

Spec: specs/012-validation-minimal-promotion/spec.md
Covers FR-005..FR-009, FR-014, US2 acceptance scenarios, edge cases.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.governance.rule_manager import RuleManager


@pytest.fixture(autouse=True)
def _reset_rule_manager_singleton() -> None:
    """Isolate RuleManager singleton between tests."""
    RuleManager.reset_instance()
    yield
    RuleManager.reset_instance()


@pytest.fixture()
def temp_states_file(tmp_path: Path) -> Path:
    """Provide a clean temporary rule states file path (not yet created)."""
    return tmp_path / "rule_states.json"


@pytest.fixture()
def audit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect audit trail to a temp file for each test."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
    return path


# ---------------------------------------------------------------------------
# US2 / FR-005 / FR-007 — default state & query interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_manager_default_state(temp_states_file: Path) -> None:
    """Unknown / missing rule defaults to shadow and is not production-active."""
    mgr = RuleManager(states_file=temp_states_file)
    assert mgr.get_rule_state("news_dedup") == "shadow"
    assert not mgr.is_active_in_production("news_dedup")
    assert mgr.get_rule_state("nonexistent_rule") == "shadow"


@pytest.mark.asyncio
async def test_rule_manager_loads_existing_states(temp_states_file: Path) -> None:
    """Existing rule_states.json is loaded into the in-memory cache on init."""
    temp_states_file.write_text(
        json.dumps({"news_dedup": "production", "other_rule": "disabled"}),
        encoding="utf-8",
    )
    mgr = RuleManager(states_file=temp_states_file)
    assert mgr.get_rule_state("news_dedup") == "production"
    assert mgr.is_active_in_production("news_dedup")
    assert mgr.get_rule_state("other_rule") == "disabled"
    assert not mgr.is_active_in_production("other_rule")


@pytest.mark.asyncio
async def test_rule_manager_ignores_invalid_state_values(temp_states_file: Path) -> None:
    """Invalid lifecycle values in the store are discarded; rule falls back to shadow."""
    temp_states_file.write_text(
        json.dumps({"news_dedup": "staging", "other": "production"}),
        encoding="utf-8",
    )
    mgr = RuleManager(states_file=temp_states_file)
    # Store is readable; unknown/invalid key defaults to shadow (not fail-safe).
    assert not mgr.is_store_unavailable()
    assert mgr.get_rule_state("news_dedup") == "shadow"
    assert mgr.get_rule_state("other") == "production"


@pytest.mark.asyncio
async def test_rule_manager_corrupt_json_fails_safe(temp_states_file: Path) -> None:
    """Corrupt state file marks store unavailable; lookups fail-safe to disabled."""
    temp_states_file.write_text("{not-valid-json", encoding="utf-8")
    mgr = RuleManager(states_file=temp_states_file)
    assert mgr.is_store_unavailable()
    assert mgr.get_rule_state("news_dedup") == "disabled"
    assert not mgr.is_active_in_production("news_dedup")


@pytest.mark.asyncio
async def test_rule_manager_non_dict_schema_fails_safe(temp_states_file: Path) -> None:
    """Non-object JSON schema marks store unavailable; lookups fail-safe to disabled."""
    temp_states_file.write_text(json.dumps(["shadow"]), encoding="utf-8")
    mgr = RuleManager(states_file=temp_states_file)
    assert mgr.is_store_unavailable()
    assert mgr.get_rule_state("news_dedup") == "disabled"
    assert not mgr.is_active_in_production("news_dedup")


@pytest.mark.asyncio
async def test_fail_safe_disabled_routes_pipeline_to_baseline(
    temp_states_file: Path,
) -> None:
    """When store is unavailable, production activation is false (baseline path)."""
    temp_states_file.write_text("{broken", encoding="utf-8")
    mgr = RuleManager(states_file=temp_states_file)
    assert mgr.get_rule_state("news_dedup") == "disabled"
    assert mgr.is_active_in_production("news_dedup") is False


@pytest.mark.asyncio
async def test_rule_state_lookup_latency_under_2ms(temp_states_file: Path) -> None:
    """FR-007 / US2.3: cached state lookups resolve in under 2 milliseconds."""
    mgr = RuleManager(states_file=temp_states_file)
    mgr._states["news_dedup"] = "production"

    # Warm-up
    mgr.get_rule_state("news_dedup")

    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        mgr.get_rule_state("news_dedup")
        mgr.is_active_in_production("news_dedup")
    elapsed_ms = (time.perf_counter() - start) * 1000
    avg_ms = elapsed_ms / iterations

    assert avg_ms < 2.0, f"Average state lookup {avg_ms:.4f}ms exceeds 2ms budget"


# ---------------------------------------------------------------------------
# US2 / FR-006 / FR-014 — promotion gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_manager_promote_enforcement(temp_states_file: Path) -> None:
    """Promotion without --checklist-approved is rejected and state is unchanged."""
    mgr = RuleManager(states_file=temp_states_file)

    with pytest.raises(ValueError) as exc:
        await mgr.promote_rule("news_dedup", checklist_approved=False, reason="Skip check")

    assert "checklist-approved" in str(exc.value).lower() or "checklist" in str(exc.value).lower()
    assert mgr.get_rule_state("news_dedup") == "shadow"


@pytest.mark.asyncio
async def test_rule_manager_promotion_success(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Successful promote updates cache, persists JSON, and writes audit event."""
    mgr = RuleManager(states_file=temp_states_file)
    # Rebind audit to the temp path (manager may have been constructed after env set)
    from app.governance.audit import AuditTrailManager

    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.promote_rule(
        rule_id="news_dedup",
        checklist_approved=True,
        reason="Checklist verified",
        actor="test_user",
    )

    assert mgr.get_rule_state("news_dedup") == "production"
    assert mgr.is_active_in_production("news_dedup")

    assert temp_states_file.exists()
    with open(temp_states_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("news_dedup") == "production"

    assert audit_path.exists()
    lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    event = json.loads(lines[-1])
    assert event["action"] == "rule.promote"
    assert event["actor"] == "test_user"
    assert event["target_type"] == "rule"
    assert event["target_id"] == "news_dedup"
    assert event["outcome"] == "success"
    assert event["details"]["previous_state"] == "shadow"
    assert event["details"]["new_state"] == "production"
    assert event["details"]["checklist_approved"] is True
    assert event["details"]["reason"] == "Checklist verified"


@pytest.mark.asyncio
async def test_promote_already_production_is_idempotent(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Re-promoting an already-production rule is a no-op (no state flip)."""
    from app.governance.audit import AuditTrailManager

    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.promote_rule("news_dedup", checklist_approved=True, reason="first")
    await mgr.promote_rule("news_dedup", checklist_approved=True, reason="second")

    assert mgr.get_rule_state("news_dedup") == "production"
    with open(temp_states_file, "r", encoding="utf-8") as f:
        assert json.load(f)["news_dedup"] == "production"


@pytest.mark.asyncio
async def test_promote_from_disabled_to_production(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Promote can restore a killed rule to production when checklist is approved."""
    from app.governance.audit import AuditTrailManager

    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.kill_rule("news_dedup", reason="temp disable", actor="ops")
    assert mgr.get_rule_state("news_dedup") == "disabled"

    await mgr.promote_rule(
        "news_dedup",
        checklist_approved=True,
        reason="re-enable after review",
        actor="ops",
    )
    assert mgr.get_rule_state("news_dedup") == "production"
    assert mgr.is_active_in_production("news_dedup")


# ---------------------------------------------------------------------------
# US2 / FR-006 / FR-009 — kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_manager_kill_switch(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Kill transitions production → disabled, persists file, and audits the event."""
    from app.governance.audit import AuditTrailManager

    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.promote_rule(
        rule_id="news_dedup",
        checklist_approved=True,
        reason="Checklist verified",
    )
    assert mgr.is_active_in_production("news_dedup")

    await mgr.kill_rule(
        rule_id="news_dedup",
        reason="Anomalous behavior detected",
        actor="tester",
    )

    assert mgr.get_rule_state("news_dedup") == "disabled"
    assert not mgr.is_active_in_production("news_dedup")

    with open(temp_states_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("news_dedup") == "disabled"

    lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    kill_events = [json.loads(ln) for ln in lines if json.loads(ln).get("action") == "rule.kill"]
    assert len(kill_events) == 1
    event = kill_events[0]
    assert event["actor"] == "tester"
    assert event["target_id"] == "news_dedup"
    assert event["details"]["previous_state"] == "production"
    assert event["details"]["new_state"] == "disabled"
    assert event["details"]["reason"] == "Anomalous behavior detected"


@pytest.mark.asyncio
async def test_kill_requires_reason(temp_states_file: Path) -> None:
    """Kill without a reason raises ValueError and leaves state unchanged."""
    mgr = RuleManager(states_file=temp_states_file)
    mgr._states["news_dedup"] = "production"

    with pytest.raises(ValueError) as exc:
        await mgr.kill_rule("news_dedup", reason="")

    assert "reason" in str(exc.value).lower()
    assert mgr.get_rule_state("news_dedup") == "production"


@pytest.mark.asyncio
async def test_kill_from_shadow_to_disabled(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Kill is allowed from shadow and still lands on disabled."""
    from app.governance.audit import AuditTrailManager

    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.kill_rule("news_dedup", reason="pre-emptively disabled", actor="admin")
    assert mgr.get_rule_state("news_dedup") == "disabled"


# ---------------------------------------------------------------------------
# Edge cases — concurrency, persistence, transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_then_kill_sequential_kill_wins(
    temp_states_file: Path, audit_path: Path
) -> None:
    """Rapid sequential promote then kill ends in disabled (kill takes effect)."""
    from app.governance.audit import AuditTrailManager

    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_path))

    await mgr.promote_rule("news_dedup", checklist_approved=True, reason="go live")
    await mgr.kill_rule("news_dedup", reason="immediate rollback")

    assert mgr.get_rule_state("news_dedup") == "disabled"
    assert not mgr.is_active_in_production("news_dedup")
    with open(temp_states_file, "r", encoding="utf-8") as f:
        assert json.load(f)["news_dedup"] == "disabled"


@pytest.mark.asyncio
async def test_state_persists_across_manager_reload(temp_states_file: Path) -> None:
    """After reset, a new RuleManager instance reloads persisted production state."""
    mgr = RuleManager(states_file=temp_states_file)
    mgr.audit_mgr = AsyncMock()
    mgr.audit_mgr.record = AsyncMock(return_value={})
    await mgr.promote_rule("news_dedup", checklist_approved=True, reason="persist me")

    RuleManager.reset_instance()
    mgr2 = RuleManager(states_file=temp_states_file)
    assert mgr2.get_rule_state("news_dedup") == "production"
    assert mgr2.is_active_in_production("news_dedup")


@pytest.mark.asyncio
async def test_concurrent_reads_are_stable(temp_states_file: Path) -> None:
    """Concurrent get_rule_state calls under lock do not raise or return garbage."""
    mgr = RuleManager(states_file=temp_states_file)
    mgr._states["news_dedup"] = "production"

    def _read() -> str:
        return mgr.get_rule_state("news_dedup")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _read(), range(50)))

    assert all(r == "production" for r in results)


@pytest.mark.asyncio
async def test_save_creates_parent_directories(tmp_path: Path) -> None:
    """State save creates missing parent directories for the states file."""
    nested = tmp_path / "nested" / "config" / "rule_states.json"
    mgr = RuleManager(states_file=nested)
    mgr.audit_mgr = AsyncMock()
    mgr.audit_mgr.record = AsyncMock(return_value={})

    await mgr.promote_rule("news_dedup", checklist_approved=True, reason="mkdir")
    assert nested.exists()
    assert json.loads(nested.read_text(encoding="utf-8"))["news_dedup"] == "production"


@pytest.mark.asyncio
async def test_is_active_in_production_false_for_shadow_and_disabled(
    temp_states_file: Path,
) -> None:
    """is_active_in_production is True only for the production lifecycle state."""
    mgr = RuleManager(states_file=temp_states_file)

    mgr._states["news_dedup"] = "shadow"
    assert not mgr.is_active_in_production("news_dedup")

    mgr._states["news_dedup"] = "disabled"
    assert not mgr.is_active_in_production("news_dedup")

    mgr._states["news_dedup"] = "production"
    assert mgr.is_active_in_production("news_dedup")
