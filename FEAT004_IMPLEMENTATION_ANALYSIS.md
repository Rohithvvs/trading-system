# FEAT-004 — Market Regime Overlay: Implementation Analysis

**Date:** 2026-07-12
**Author:** Principal Repository Engineer
**Status:** Pre-implementation analysis — code is complete but never wired
**Reference Spec:** `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md`
**Reference Breakdown:** `FEAT-004_IMPLEMENTATION_BREAKDOWN.md`

---

## 1. Current Implementation Status

| Component | Status | File | Lines |
|-----------|--------|------|-------|
| Specification | Complete | `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md` | 293 |
| Implementation breakdown | Complete | `FEAT-004_IMPLEMENTATION_BREAKDOWN.md` | 428 |
| Core service (7 helpers) | **Complete** | `backend/app/services/feat004_regime_overlay.py` | 741 |
| Unit tests (24 test cases) | **Complete** | `backend/app/tests/test_feat004_regime_overlay.py` | 535 |
| Hook in RecommendationService | **Complete** | `backend/app/services/recommendation_service.py:94-108` | — |
| Monitoring checklist (19 metrics) | Complete | `feat004_monitoring_checklist.csv` | 19 |
| ADR (Option C — Selected) | Complete | `docs/adr/ADR-002_market_regime_consolidation.md` | 236 |

**Critical finding: FEAT-004 is fully implemented but NEVER executes.**

The service module (`feat004_regime_overlay.py`) has all 7 required helper functions, the `apply_feat004_regime_overlay()` top-level orchestrator, comprehensive safe-fallback logic (never raises), and the SHADOW/ACTIVE stage gating. The hook in `RecommendationService.build()` correctly isolates the overlay after composite score computation and before the Strict Buy Gate, preserving `raw_technical_score` for gate use.

**The single blocking gap:** No caller passes `feat004_config`, `benchmark_ohlcv`, `sector_mapping`, or `sector_ohlcv_cache` to `RecommendationService.build()`. As a result, `feat004_config` defaults to `None` → coerced to `{"enabled": False}`, and the overlay always early-returns with an ABSTAINED log payload.

---

## 2. Existing Files Already Related to FEAT-004

### Core implementation (complete — no changes needed)
| File | Role |
|------|------|
| `backend/app/services/feat004_regime_overlay.py` | 7 helper functions, top-level orchestrator, safe-fallback, SHADOW/ACTIVE gating |
| `backend/app/services/recommendation_service.py` | Hook point at lines 94-108, imports and calls overlay |

### Test suite (complete — no changes needed)
| File | Role |
|------|------|
| `backend/app/tests/test_feat004_regime_overlay.py` | 24 test cases covering all 20 mandatory TC + 4 bonus |
| `feat004_monitoring_checklist.csv` | 19/19 metrics PASSED |

### Documentation (complete)
| File | Role |
|------|------|
| `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md` | v1.0 specification |
| `FEAT-004_IMPLEMENTATION_BREAKDOWN.md` | Implementation guide with function signatures |
| `docs/adr/ADR-002_market_regime_consolidation.md` | ADR selecting Option C |

---

## 3. Files That Require Modification

| # | File | Change | Priority |
|---|------|--------|----------|
| 1 | `backend/app/config/settings.py` | Add `feat004` config section (enabled, stage, benchmark_symbols, score_deltas, etc.) | **P0 — prerequisite** |
| 2 | `backend/app/agents/recommendation_agent.py` | Accept and forward `feat004_config`, `benchmark_ohlcv`, `sector_mapping`, `sector_ohlcv_cache` to `RecommendationService.build()` | **P0 — the wiring gap** |
| 3 | `backend/app/agents/orchestrator_agent.py` | Fetch benchmark OHLCV, load sector mapping, pass FEAT-004 kwargs to `RecommendationAgent.run()` | **P0 — data plumbing** |
| 4 | `backend/app/agents/orchestrator_agent.py` | `_unavailable_analysis_result()` — pass FEAT-004 kwargs to `RecommendationService.build()` for consistency | **P1 — consistency** |
| 5 | `backend/app/schemas/analysis.py` | Optionally formalize `feat004` as a first-class schema field (currently dynamic attribute) | **P2 — nice to have** |
| 6 | `docs/adr/ADR-002_market_regime_consolidation.md` | Document that Option C implementation is proceeding | **P1 — governance** |

### Detail on each required modification

#### File 1: `settings.py` (new config section)

Must be added alongside the existing `feat008` block (lines 115-118). The module already has internal defaults at `feat004_regime_overlay.py:587-597`. These should be extracted to settings:

```yaml
# Proposed settings structure (Python nested dict approach):
feat004:
  enabled: false                      # Master switch
  stage: "SHADOW"                     # SHADOW → log-only, ACTIVE → apply deltas
  stage_shadow_min_sessions: 30       # Minimum sessions before ACTIVE activation
  benchmark_symbols:                  # Priority-ordered index symbols
    - "NIFTY500"
    - "NIFTY50"
  min_benchmark_candles: 220
  staleness_limit_days: 1
  sector_mapping_enabled: false       # v1 metadata only
  sector_min_candles: 50
  score_deltas:
    FAV: 2.0
    NEU: 0.0
    CAU: -3.0
    DEF: -5.0
    ABS: 0.0
  buy_downgrade_thresholds:
    CAU: 74.0
    DEF: 77.0
  favorable_cap_below_buy: true
  buy_threshold: 72.0
```

#### File 2: `recommendation_agent.py` (forward parameters)

Current signature (line 22-28):
```python
def run(self, symbol, technical_results, sentiment_label, sentiment_score,
        fundamental_result, backtests, candles_by_mode) -> FinalRecommendation:
```

Required signature:
```python
def run(self, symbol, technical_results, sentiment_label, sentiment_score,
        fundamental_result, backtests, candles_by_mode,
        feat004_config=None, benchmark_ohlcv=None,
        sector_mapping=None, sector_ohlcv_cache=None) -> FinalRecommendation:
```

Internal change at line 42 — pass all feat004 params to `self.recommendation_service.build()`.

#### File 3: `orchestrator_agent.py` (data plumbing)

Three changes needed in `_analyze_symbol_post_bulk`:

**a) Fetch benchmark OHLCV** (after line 530, alongside other async operations):
```python
# Pre-fetch benchmark index OHLCV for FEAT-004 market regime overlay
if settings.feat004_enabled:
    benchmark_ohlcv = await _fetch_benchmark_for_feat004(settings.feat004_benchmark_symbols)
else:
    benchmark_ohlcv = None
```

**b) Load sector mapping** (if sector_mapping_enabled):
```python
sector_mapping = _load_sector_mapping() if settings.feat004_sector_mapping_enabled else None
sector_ohlcv_cache = {}  # Build per-session if enabled
```

**c) Pass to RecommendationAgent** (line 583):
```python
recommendation = await asyncio.to_thread(
    self.recommendation_agent.run,
    symbol, ..., backtests=composite_backtests, candles_by_mode,
    feat004_config=settings.feat004,           # New
    benchmark_ohlcv=benchmark_ohlcv,            # New
    sector_mapping=sector_mapping,              # New
    sector_ohlcv_cache=sector_ohlcv_cache,      # New
)
```

#### File 4: `orchestrator_agent.py` — fallback path consistency

`_unavailable_analysis_result()` (line 885) directly calls `recommendation_service.build()`. Must also pass FEAT-004 kwargs for consistent behavior, even though the unavailable-data path always produces REJECT with 0.0 score.

#### File 5: `schemas/analysis.py` (optional formalization)

Currently `feat004` log is attached as a dynamic attribute on `FinalRecommendation` (recommendation_service.py:161-164). Formalizing it in the schema would improve type safety and documentation. Low priority — the dynamic attribute works correctly.

---

## 4. Files That Must NOT Change

| File | Reason |
|------|--------|
| `backend/app/services/feat004_regime_overlay.py` | Complete and tested. No changes needed. |
| `backend/app/tests/test_feat004_regime_overlay.py` | Complete. Tests pass independently. |
| `backend/app/services/backtest_service.py` | FEAT-008 scope. Unrelated. |
| `backend/app/services/recommendation_service.py` | Hook already exists and works. No changes needed. |
| `backend/app/services/market_permission_service.py` | SR-004 scope. Handled by ADR-002. |
| `backend/app/services/sector_rs_service.py` | SR-003 scope. Unrelated. |
| `backend/app/agents/backtest_agent.py` | FEAT-008 scope. Unrelated. |
| `backend/app/agents/technical_analysis_agent.py` | Unrelated. |
| `backend/app/agents/news_analysis_agent.py` | Unrelated. |
| `backend/app/agents/fundamental_analysis_agent.py` | Unrelated. |
| `backend/app/agents/ranking_agent.py` | Unrelated. |
| `FEAT-008_REALISTIC_TRADE_EXECUTION_MODEL.md` | FEAT-008 scope. Complete. |
| `backend/app/tests/test_backtest_realism.py` | FEAT-008 scope. Complete. |

---

## 5. Current Recommendation Flow

```
[OHLCV pre-fetch] → [Bulk Technical Analysis (vectorized)]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase C: Concurrent Agent Execution                         │
│   ├── BacktestAgent.run()        → List[BacktestResult]     │
│   ├── NewsAnalysisAgent.run()    → sentiment_score, label   │
│   └── FundamentalAnalysisAgent   → FundamentalAnalysisResult│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase F: RecommendationAgent.run()                          │
│   ├── LLMService.build_reasoning() → reasoning dict         │
│   └── RecommendationService.build()                         │
│        ├── Composite score (weighted dynamic sum)            │
│        ├── Initial label (BUY/WATCH/REJECT)                  │
│        ├── [FEAT-004 Overlay] ◄═══ DISABLED (gap!)          │
│        └── FinalRecommendation                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase I: Strict Buy Gate (_enforce_strict_buy_gate)         │
│   Checks: strong_live_data AND strong_technical (>=75)      │
│           AND strong_execution (RR >= 1.25)                  │
│   May downgrade BUY → WATCH                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase J: SR-003 Sector Overlay                               │
│   SectorRelativeStrengthService.evaluate_sector_overlay()    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase K: SR-004 Market Permission                            │
│   MarketPermissionService.evaluate_market_permission()       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase L: Build Challenger Recommendation                     │
│   Start: copy of original recommendation                     │
│   Apply SR-003 downgrade (if triggered)                     │
│   Apply SR-004 downgrade (if new_entry_allowed=False)        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
  StockAnalysisResult { recommendation, challenger_recommendation,
                        sector_overlay, market_regime,
                        confidence_breakdown }
```

---

## 6. Where FEAT-004 Should Integrate

### ADR-002 requires FEAT-004 to be PRE-GATE

Per ADR-002 Option C (the selected option), FEAT-004 and SR-004 have formally separated responsibilities:

| Feature | Placement | Responsibility |
|---------|-----------|----------------|
| **FEAT-004** | Pre-Gate | Trend-regime score modifier using benchmark SMA50/SMA200/SMA20-slope/ROC20 |
| **SR-004** | Post-Gate | Volatility/breadth permission gate using NIFTY50 EMA50 + India VIX + breadth proxy |

**Integration point:** `RecommendationService.build()` lines 94-108 (already exists — just needs wiring).

### Detailed integration plan

**Step A: Wire the existing hook (P0)**

The hook already exists in `RecommendationService.build()` at lines 94-108. The overlay function `apply_feat004_regime_overlay()` is already imported, called, and correctly positioned after composite score computation and before final output. The only missing piece is that the callers don't pass the required data.

**Step B: Add config section to settings.py (P0)**

Add `feat004` config block to the existing `Settings` model. The module's internal defaults (lines 587-597 of `feat004_regime_overlay.py`) become the config defaults.

**Step C: Modify RecommendationAgent.run() signature (P0)**

Add optional `feat004_config`, `benchmark_ohlcv`, `sector_mapping`, `sector_ohlcv_cache` parameters with `None` defaults. Forward them to `RecommendationService.build()`.

**Step D: Add benchmark fetch to orchestrator (P0)**

In `_analyze_symbol_post_bulk`, conditionally fetch benchmark index OHLCV data. The `resolve_benchmark_ohlcv()` function in `feat004_regime_overlay.py` already handles all the fetch logic — the orchestrator just needs to call it.

**Step E: Wire unavailable-data path (P1)**

`_unavailable_analysis_result()` directly calls `recommendation_service.build()` without going through `RecommendationAgent.run()`. Must also pass FEAT-004 kwargs.

**Step F: Enable per checking data (P2)**

The `feat004_monitoring_checklist.csv` shows 19/19 metrics PASSED, suggesting backtest validation has been completed. Per FEAT-005 §9.2, evidence must be promoted from Level C to Level B before ACTIVE activation. This requires:
- 30+ sessions in SHADOW mode producing clean logs
- Review of log patterns against expected regime frequencies
- Decision gate: System Owner approval to change `stage: "ACTIVE"`

---

## 7. Existing Configuration

### What exists (settings.py)

```python
# Lines 115-118 — only feat008 section present
feat008_enabled: bool = True
feat008_execution_model: str = "REALISTIC"
feat008_composite_uses_realistic: bool = True
feat008_cost_scenario: str = "BASE_COST"
```

### What is needed (FEAT-004 config)

```yaml
feat004_enabled: bool = False
feat004_stage: str = "SHADOW"               # SHADOW | ACTIVE
feat004_benchmark_symbols: list[str]        # ["NIFTY500", "NIFTY50"]
feat004_min_benchmark_candles: int = 220
feat004_staleness_limit_days: int = 1
feat004_sector_mapping_enabled: bool = False
feat004_sector_min_candles: int = 50
feat004_score_deltas_FAV: float = 2.0
feat004_score_deltas_NEU: float = 0.0
feat004_score_deltas_CAU: float = -3.0
feat004_score_deltas_DEF: float = -5.0
feat004_score_deltas_ABS: float = 0.0
feat004_buy_downgrade_threshold_CAU: float = 74.0
feat004_buy_downgrade_threshold_DEF: float = 77.0
feat004_favorable_cap_below_buy: bool = True
feat004_buy_threshold: float = 72.0
```

### Internal module defaults (already hardcoded)

The `apply_feat004_regime_overlay()` function at lines 587-597 of `feat004_regime_overlay.py` uses these exact values as fallback when `feat004_config` is `None`. These should be promoted to settings and the module should read from settings instead.

---

## 8. Existing Helper Functions

### `feat004_regime_overlay.py` — 7 complete helpers

| # | Function | Lines | Purpose | Status |
|---|----------|-------|---------|--------|
| 1 | `resolve_benchmark_ohlcv()` | 42-106 | Fetch index OHLCV with prioritization, min-candles check, staleness check. Never raises. | Complete |
| 2 | `compute_benchmark_indicators()` | 112-178 | SMA50, SMA200, SMA20-slope, ROC20. Safe defaults on failure. | Complete |
| 3 | `classify_market_regime()` | 185-234 | 5-state classifier (FAV/NEU/CAU/DEF/ABS) with top-down priority. | Complete |
| 4 | `apply_regime_score_modifier()` | 239-300 | Score deltas, FAV cap, BUY→WATCH downgrade, SHADOW/ACTIVE gating. | Complete |
| 5 | `compute_sector_strength()` | 305-403 | Metadata-only sector RS (ratio formula). v1 feature. | Complete |
| 6 | `build_feat004_log_payload()` | 409-537 | 17-field log schema, human-readable explanation string. | Complete |
| 7 | `apply_feat004_regime_overlay()` | 544-706 | Top-level orchestrator. Wraps all helpers. Outer exception boundary. | Complete |

### Internal utility
| Function | Lines | Purpose |
|----------|-------|---------|
| `_minimal_abstained_payload()` | 712-741 | Safe fallback when overlay is disabled or errors occur |

### `resolve_benchmark_ohlcv()` — key detail

This function needs a data fetcher to work. Currently it accepts a `fetcher` parameter that, if provided, is called to get candles. The orchestrator would need to provide the `FyersService` as this fetcher. The function already handles:
- Prioritization (try NIFTY500, fall back to NIFTY50)
- Minimum candle count check (220 default)
- Staleness check (1 day default)
- Returns `None` on fetch failure (safe fallback)

---

## 9. Existing Tests

### Unit test suite — 24 tests (all pass independently)

**File:** `backend/app/tests/test_feat004_regime_overlay.py` (535 lines)

| TC # | Test Name | What It Verifies |
|------|-----------|-----------------|
| TC-1 | `test_regime_favorable` | SMA50 > SMA200 + rising SMA20 + positive ROC20 → FAVORABLE |
| TC-2 | `test_regime_neutral` | SMA50 > SMA200, flat/no criteria → NEUTRAL |
| TC-3 | `test_regime_cautious` | SMA50 < SMA200, but no additional bearish signals → CAUTIOUS |
| TC-4 | `test_regime_defensive` | SMA50 < SMA200 + falling SMA20 + negative ROC20 → DEFENSIVE |
| TC-5 | `test_regime_abstained_none_input` | Missing benchmark data yields ABSTAINED |
| TC-6 | `test_shadow_mode_no_score_change` | SHADOW stage returns original score unmodified |
| TC-7 | `test_active_cautious_penalty` | ACTIVE CAUTIOUS → -3.0 delta applied |
| TC-8 | `test_active_defensive_penalty` | ACTIVE DEFENSIVE → -5.0 delta applied |
| TC-9 | `test_favorable_cap_prevents_watch_to_buy` | FAV cap caps non-BUY scores at 71.99 |
| TC-10 | `test_favorable_no_cap_when_already_buy` | FAV cap does not affect scores already BUY (>=72) |
| TC-11 | `test_benchmark_unavailable_defaults_to_abs` | Failed benchmark fetch → ABSTAINED |
| TC-12 | `test_stale_benchmark_returns_abstained_reason` | Stale data returns ABSTAINED with reason |
| TC-13 | `test_sector_no_mapping_returns_unknown` | Unknown sector → UNKNOWN |
| TC-14 | `test_sector_symbol_not_in_mapping` | Symbol not in mapping → UNKNOWN |
| TC-15 | `test_sector_strong` | sector_roc20 / bm_roc20 >= 1.2 → STRONG |
| TC-16 | `test_sector_weak` | sector_roc20 / bm_roc20 <= 0.8 → WEAK |
| TC-17 | `test_outer_exception_returns_original_score` | Outer exception boundary returns original score unmodified |
| TC-18 | `test_log_payload_always_complete_on_abstained_path` | ABSTAINED path produces complete log payload |
| TC-19 | `test_strict_buy_gate_receives_unmodified_raw_ta_score` | `raw_technical_score` is never mutated by FEAT-004 |
| TC-20 | `test_reject_label_unchanged_by_regime` | REJECT label is immutable (never upgraded) |
| Bonus | `test_compute_benchmark_indicators_rising_df` | Deterministic indicator computation on known data |
| Bonus | `test_compute_benchmark_indicators_falling_df` | Deterministic indicator computation on known data |
| Bonus | `test_resolve_benchmark_ohlcv_success` | Successful benchmark OHLCV resolve |
| Bonus | `test_resolve_benchmark_ohlcv_insufficient_history` | Returns None for insufficient candles |
| Bonus | `test_resolve_benchmark_ohlcv_fetcher_raises` | Returns None when fetcher raises |

### Integration tests (to be added during wiring)

The implementation will need additional integration tests that verify:
- FEAT-004 config flows from settings → orchestrator → recommendation_agent → recommendation_service
- Benchmark OHLCV is correctly fetched and passed
- Default (disabled) state produces same output as before
- Shadow mode produces same output as disabled but logs
- Active mode applies correct deltas and downgrades

---

## 10. Existing Logging

### FEAT-004 module logging

The `feat004_regime_overlay.py` module uses the standard `get_logger()` pattern:

```python
from ..utils import get_logger
logger = get_logger("app.feat004_regime_overlay")
```

Log calls at key decision points:
- `resolve_benchmark_ohlcv`: logs fetch attempts, fallbacks, failures (DEBUG/INFO/WARNING)
- `classify_market_regime`: logs classification decision with indicator values (INFO)
- `apply_regime_score_modifier`: logs SHADOW passthrough vs ACTIVE modification (INFO)
- `apply_feat004_regime_overlay`: logs the final summary with regime, delta, final score (INFO)
- Outer exception boundary: logs full traceback on unexpected errors (ERROR)

### Log payload (17 fields)

The `build_feat004_log_payload()` function produces a structured dict with 17 fields:
- `session_id`, `symbol`, `regime`, `score_delta`, `score_before`, `score_after`
- `label_before`, `label_after`, `stage`, `downgraded`, `capped`
- `sma50`, `sma200`, `sma20_slope`, `roc20`, `reason`
- `sector`, `explanation` (human-readable string)

This payload is attached to `FinalRecommendation` as a dynamic `feat004` attribute.

### Orchestrator logging

The orchestrator (`orchestrator_agent.py`) uses:
```python
self.logger = get_logger("app.orchestrator")
```

Key log points that should include FEAT-004 context (currently do not):
- Line 683-691: `"Completed symbol analysis"` — should include FEAT-004 regime if active
- Line 904: `StockAnalysisResult` assembly — no FEAT-004 fields present

---

## 11. Existing Feature Flags

### FEAT-008 flags (in settings.py, lines 115-118)
```python
feat008_enabled: bool = True
feat008_execution_model: str = "REALISTIC"
feat008_composite_uses_realistic: bool = True
feat008_cost_scenario: str = "BASE_COST"
```

### FEAT-004 flags (to be added)
```python
feat004_enabled: bool = False           # Master on/off
feat004_stage: str = "SHADOW"           # SHADOW (log-only) vs ACTIVE (apply deltas)
feat004_sector_mapping_enabled: bool = False  # Metadata-only in v1
```

### Other feature flags
- `settings.py` has no other feature-specific sections (FEAT-005, FEAT-006, FEAT-007 are not config-flagged in the same way)
- SR-003 and SR-004 are always active (no config flags)
- The orchestrator's `_enforce_strict_buy_gate` is always active (no config flag)

---

## 12. Runtime Dependencies

### Data dependencies (must be available at runtime)

| Dependency | Source | Format | Required for |
|------------|--------|--------|--------------|
| Benchmark index OHLCV | `FyersService.get_ohlcv()` | `list[OHLCVPoint]` | Regime classification |
| NIFTY500 or NIFTY50 candles | Live fetch or cache | Daily resolution, 220+ candles | SMA50/SMA200/ROC20 computation |
| Sector mapping | `sector_mappings.json` | `dict[symbol → sector_index]` | Sector strength (v1 metadata) |
| Sector index OHLCV | `FyersService.get_ohlcv()` | `list[OHLCVPoint]` per sector | Sector strength (v1 metadata) |

### Service dependencies (already available in the orchestrator)

| Service | Available at | Used for |
|---------|-------------|----------|
| `FyersService` | `self.fyers_service` (orchestrator line 43) | Fetching benchmark and sector OHLCV |
| `settings` | `from ..config import settings` | Reading config values |
| `get_logger` | `from ..utils import get_logger` | Logging |

### Module dependencies (already imported by existing code)

| Module | Imported by | Purpose |
|--------|------------|---------|
| `feat004_regime_overlay` | `recommendation_service.py:17` | `apply_feat004_regime_overlay` function |
| `numpy` | `feat004_regime_overlay` | Indicator computation |
| `pandas` | `feat004_regime_overlay` | DataFrame operations |

### No new dependencies needed

All required dependencies are already present in the codebase. FEAT-004 reuses the existing `FyersService` for data fetching and the existing settings/config infrastructure for configuration.

---

## 13. Potential Regression Risks

### Risk 1: Score modification changes recommendation outcomes (HIGH)

**Description:** When FEAT-004 is enabled in ACTIVE stage, score deltas (-3.0 CAU, -5.0 DEF) can change a BUY to WATCH or a WATCH to REJECT. This directly changes user-facing recommendations.

**Mitigation:**
- Start with `enabled=False`, then `stage=SHADOW` for 30+ sessions
- Compare SHADOW-mode log patterns against pre-FEAT-004 baselines
- Only activate after reviewing that regime frequencies and downgrade rates match expected backtest results
- The `monitoring_checklist.csv` already shows 19/19 metrics PASSED from backtest

### Risk 2: Benchmark data fetch failure (MEDIUM)

**Description:** If the benchmark index (NIFTY500/NIFTY50) cannot be fetched:
- `resolve_benchmark_ohlcv()` returns `None`
- The overlay falls back to ABSTAINED
- Original score passes through unchanged

**Mitigation:** This is a safe default. The module is designed so that ANY failure → ABSTAINED → original score returned. No crash, no bad data.

### Risk 3: Overlap with SR-004 (Market Permission) — HIGH

**Description:** Both FEAT-004 and SR-004 classify "market regime" but use different inputs and produce different outputs. They overlap in vocabulary (both use "DEFENSIVE" and "CAUTIOUS" states). ADR-002 Option C resolves this by giving them separate responsibilities (FEAT-004 = pre-Gate trend modifier, SR-004 = post-Gate volatility/breadth gate), but the state rename for SR-004 (to avoid vocabulary collision) is not yet implemented.

**Mitigation:**
- Implement ADR-002 Option C as specified
- Rename SR-004 states: FAVORABLE→PERMISSIVE, CAUTIOUS→RESTRICTED, HIGHRISK→BLOCKED, DEFENSIVE→CLOSED
- Document the clear boundary: FEAT-004 affects the composite score, SR-004 affects new_entry_allowed only

### Risk 4: Performance impact of additional data fetching (LOW)

**Description:** FEAT-004 requires fetching benchmark index OHLCV (220+ daily candles for NIFTY500/NIFTY50). This adds one additional `FyersService` call per analysis session.

**Mitigation:**
- Cache benchmark OHLCV per session (don't re-fetch per symbol)
- The orchestrator already makes multiple `FyersService` calls — one more is negligible
- Benchmark fetch runs once per batch, not per symbol

### Risk 5: FEAT-008 composite_uses_realistic interaction (LOW)

**Description:** FEAT-004 modifies the composite score, which is computed using either realistic (Pass 2) or legacy (Pass 1) returns depending on `composite_uses_realistic`. The overlay doesn't care which source the score comes from — it just adjusts the final number.

**Mitigation:** Already safe — FEAT-004 hooks AFTER the composite is computed, not before. The overlay is agnostic to which backtest source fed the composite.

---

## 14. Missing Prerequisites

### Critical blockers (must resolve before implementation begins)

| Blocker | Description | Resolution |
|---------|-------------|------------|
| **B1: ADR-002 System Owner Decision** | ADR-002 recommends Option C but this has not been formally accepted. The implementation should not proceed without explicit system owner approval. | Obtain written acceptance of ADR-002 Option C via the ADR process |
| **B2: SR-004 State Rename** | Per Option C, SR-004 states must be renamed to avoid vocabulary collision with FEAT-004 states. This rename touches orchestrator code and downstream consumers. | Implement SR-004 state rename as a prerequisite micro-task (touches `market_permission_service.py` states and all references in `orchestrator_agent.py`) |

### Non-blocking prerequisites (can proceed in parallel)

| Prerequisite | Description | Priority |
|-------------|-------------|----------|
| **P1: Monitoring checklist review** | The `feat004_monitoring_checklist.csv` shows 19/19 metrics PASSED. These should be reviewed to confirm the backtest validation threshold has been met. | P1 |
| **P2: Settings extraction** | The module's internal defaults should be extracted to settings before wiring, ensuring a single source of truth. | P1 |
| **P3: Benchmark fetch caching strategy** | Decide whether to cache benchmark OHLCV per session or per request. Per session is simpler and sufficient. | P2 |

---

## 15. Recommended Implementation Order

### Phase 1: Infrastructure (non-disruptive, no behavioral change)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 1.1 | Add `feat004` config section to `settings.py` with `enabled=False` default | `settings.py` | Small | None |
| 1.2 | Update `feat004_regime_overlay.py` to read from settings instead of hardcoded defaults | `feat004_regime_overlay.py` | Small | None |
| 1.3 | (Optional) Implement SR-004 state rename per ADR-002 | `market_permission_service.py`, `orchestrator_agent.py` | Medium | Medium |

### Phase 2: Wiring (still disabled, no behavioral change)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 2.1 | Modify `RecommendationAgent.run()` signature to accept FEAT-004 kwargs (all optional, defaults None) | `recommendation_agent.py` | Small | None |
| 2.2 | Add benchmark OHLCV fetch to orchestrator (conditional on `feat004_enabled`) | `orchestrator_agent.py` | Medium | Low |
| 2.3 | Wire FEAT-004 kwargs through orchestrator → recommendation_agent → recommendation_service | `orchestrator_agent.py`, `recommendation_agent.py` | Small | Low |
| 2.4 | Wire FEAT-004 kwargs to `_unavailable_analysis_result()` fallback path | `orchestrator_agent.py` | Small | None |
| 2.5 | Add integration tests for wiring (config flow, benchmark fetch, shadow passthrough) | `test_feat004_regime_overlay.py` or new file | Medium | None |

### Phase 3: Shadow Deployment (enabled in SHADOW, no score changes)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 3.1 | Deploy with `feat004_enabled=True`, `feat004_stage=SHADOW` | Config only | None | Low |
| 3.2 | Monitor log output for 30+ sessions | Observability | Ongoing | None |
| 3.3 | Verify 19 monitoring checklist metrics match backtest predictions | Review | Medium | None |
| 3.4 | Document SHADOW-mode results in evidence hierarchy (FEAT-005 §9.2: Level C → B) | Documentation | Small | None |

### Phase 4: Activation (enabled in ACTIVE, score changes apply)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 4.1 | System Owner decision gate: approve activation | Governance | None | N/A |
| 4.2 | Deploy with `feat004_stage=ACTIVE` | Config only | None | High |
| 4.3 | Monitor recommendation distribution changes for 5+ sessions | Observability | Ongoing | Medium |
| 4.4 | Rollback to SHADOW if imbalance detected (rollback criteria in spec §17) | Config only | None | N/A |

---

## Appendix A: FEAT-004 vs SR-004 Comparison

| Dimension | FEAT-004 | SR-004 |
|-----------|----------|--------|
| Input data | Benchmark index (NIFTY500/NIFTY50) SMA50/SMA200/SMA20-slope/ROC20 | NIFTY50 close vs EMA50 + India VIX + breadth proxy |
| Signal type | Pure trend structure (price vs moving averages) | Volatility + breadth + simple trend |
| States | FAVORABLE / NEUTRAL / CAUTIOUS / DEFENSIVE / ABSTAINED (5) | FAVORABLE / CAUTIOUS / HIGHRISK / DEFENSIVE (4) |
| Effect on score | Continuous delta (-5 to +2) applied to composite score | No score delta; binary `new_entry_allowed` + flat 71.0 cap on challenger |
| Effect on action | Can downgrade BUY → WATCH (thresholds at 74/77) | Can downgrade BUY → WATCH via challenger |
| Placement | Pre-Gate (on base composite) | Post-Gate (on challenger) |
| Status | Code complete, not wired | Live, in production |

---

## Appendix B: ADR-002 Option C Specification

```
FEAT-004: Pre-Gate trend-regime score modifier
  → Modifies composite score before it reaches the Strict Buy Gate
  → Uses benchmark SMA50/SMA200/SMA20-slope/ROC20
  → 5 states: FAV/NEU/CAU/DEF/ABS
  → Score deltas: +2.0 / 0.0 / -3.0 / -5.0 / 0.0
  → BUY downgrade thresholds at CAU=74.0, DEF=77.0
  → FAV cap at 71.99 for non-BUY scores

SR-004: Post-Gate volatility/breadth permission gate
  → Operates on challenger recommendation after the gate
  → Uses NIFTY50 EMA50 + India VIX + breadth proxy
  → 4 states: PERMISSIVE / RESTRICTED / BLOCKED / CLOSED (renamed)
  → Binary: new_entry_allowed = True/False
  → Flat 71.0 score cap on challenger when blocked

Boundary: FEAT-004 modifies the score before gate evaluation.
          SR-004 modifies the challenger after gate evaluation.
          They do NOT overlap in their effect on the same output.
```

---

## Appendix C: Key Line References

| Component | File | Lines |
|-----------|------|-------|
| **FEAT-004 overlay entry point** | `recommendation_service.py` | 94-108 |
| **FEAT-004 disabled default** | `recommendation_service.py` | 99 |
| **RecommendationAgent.run() (gap)** | `recommendation_agent.py` | 22-50 |
| **Orchestrator primary path** | `orchestrator_agent.py` | 480-701 |
| **Orchestrator fallback path** | `orchestrator_agent.py` | 885-948 |
| **SR-003 sector overlay** | `orchestrator_agent.py` | 604-614 |
| **SR-004 market permission** | `orchestrator_agent.py` | 616-619 |
| **Strict Buy Gate** | `orchestrator_agent.py` | 959-1054 |
| **FEAT-008 config** | `settings.py` | 115-118 |
| **FEAT-004 config (gap)** | `settings.py` | N/A |
| **apply_regime_overlay() defaults** | `feat004_regime_overlay.py` | 587-597 |
| **FEAT-004 test suite** | `test_feat004_regime_overlay.py` | 1-535 |
| **ADR-002** | `docs/adr/ADR-002_market_regime_consolidation.md` | 1-236 |
