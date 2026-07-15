# FEAT-007 Synchronization Report

**Date:** 2026-07-12
**Author:** Principal Software Architect
**Status:** Pre-implementation synchronization analysis
**ADR-003 Status:** Accepted (Option C-Revised) — **final, not reconsidered**
**Decision:** Difference formula (`sector_roc20 − bm_roc20`) is canonical. Ratio formula (`sector_roc20 / bm_roc20`) is rejected.

---

## 1. Current Implementation Status

| Component | Status | File | Formula |
|-----------|--------|------|---------|
| FEAT-007 specification | v1.0 — **STALE** (specifies ratio) | `FEAT-007_SECTOR_RELATIVE_STRENGTH.md` | Ratio ❌ |
| ADR-003 | Accepted — authoritative | `docs/adr/ADR-003_sector_relative_strength_formula.md` | Difference ✅ |
| Evidence report | Final — 10,827 observations | `docs/adr/EVIDENCE_REPORT_SR_formula_comparison.md` | Rejects ratio ✅ |
| SR-003 (live) | Production — reference implementation | `backend/app/services/sector_rs_service.py` | Difference ✅ |
| `compute_sector_strength` (dead) | Inert — metadata-only inside FEAT-004 | `backend/app/services/feat004_regime_overlay.py:305-403` | Ratio ❌ |
| FEAT-007 score modifier | **Not implemented** | — | — |
| FEAT-007 configuration | **Not implemented** | — | — |
| FEAT-007 tests | **Not implemented** | — | — |

**Summary:** The FEAT-007 specification (v1.0) still assumes the ratio formula throughout. ADR-003 mandates a revision that has not been performed. The live SR-003 code already uses the correct difference formula. No FEAT-007 production code exists yet.

---

## 2. Every Place Where FEAT-007 Spec Still Assumes the Ratio Formula

### Mismatch 1 — Section 9.1: Input definition

| Field | Value |
|-------|-------|
| **Section** | §9.1 Inputs (line 150) |
| **Current wording** | `relative_strength_ratio: float \| None — sector_roc20 / benchmark_roc20, with FEAT-004 §6 safe-divide (if benchmark_roc20 == 0, ratio = 1.0)` |
| **Required wording** | `sector_rs_value: float \| None — sector_roc20 − benchmark_roc20 (percentage points). No safe-divide needed; the difference formula is well-defined at all benchmark values.` |
| **Why it changes** | ADR-003 §0: "the difference formula (`sector_roc20 − bm_roc20`) is the canonical sector-relative-strength formula." The ratio input and its safe-divide fallback are eliminated. |
| **Implementation impact** | The FEAT-007 overlay function must accept `sector_rs_value` (a difference in percentage points) instead of `relative_strength_ratio` (a unitless multiplier). The safe-divide-to-1.0 fallback is removed entirely. |

### Mismatch 2 — Section 9.2: Sector regime classification thresholds

| Field | Value |
|-------|-------|
| **Section** | §9.2 Sector regime classification (lines 158-165) |
| **Current wording** | Four states on ratio scale: `UNKNOWN` if ratio is None; `STRONG` if ratio > 1.10; `NEUTRAL` if 0.90 ≤ ratio ≤ 1.10; `WEAK` if ratio < 0.90` |
| **Required wording** | States on the difference scale. Per ADR-003 §0, the binary WEAK/STRENGTH classification from SR-003 is the starting point. The three-state STRONG/NEUTRAL/WEAK mechanic is a "separate, evidence-backed step" (ADR-003 §0). The v1.1 revision should adopt: `UNKNOWN` if value is None; `WEAK` if value < 0 (underperforming benchmark); `STRENGTH` if value ≥ 0 (matching SR-003's binary classification). The optional three-state upgrade (adding NEUTRAL with a ±X pp band) is deferred to a future revision. |
| **Why it changes** | ADR-003 §0 explicitly states mechanic upgrades (including three-state) are a "separate, evidence-backed step." The ratio thresholds (1.10/0.90) are meaningless on the difference scale. SR-003's binary `sector_rs_20 < 0` → WEAK is the proven, audited classification. |
| **Implementation impact** | Classification logic changes from ratio thresholds (1.10/0.90) to a difference threshold (0.0). The NEUTRAL state is removed for v1.1 (or preserved with a proposed ±1.0 pp band pending System Owner decision — see GOVERNANCE_CONSISTENCY_REVIEW §5.4). |

### Mismatch 3 — Section 9.3: Score modifier table references ratio states

| Field | Value |
|-------|-------|
| **Section** | §9.3 Score modifier (lines 171-176) |
| **Current wording** | Table maps `STRONG` / `NEUTRAL` / `WEAK` / `UNKNOWN` to score deltas (+1.5 / 0.0 / -3.0 / 0.0) with BUY→WATCH downgrade threshold at score < 74 for WEAK |
| **Required wording** | Same score deltas and downgrade threshold, but the state names must align with the difference-formula classification. If binary: `STRENGTH` (+1.5, no downgrade), `WEAK` (-3.0, downgrade if < 74), `UNKNOWN` (0.0, no effect). If three-state is retained: add `NEUTRAL` (0.0, no effect) with difference-scale thresholds. The score-delta mechanic itself is **unchanged** per ADR-003's scope discipline. |
| **Why it changes** | ADR-003 §0: "any mechanic upgrade (three-state, score deltas, pre-Gate placement) is a separate, evidence-backed step." The score deltas (+1.5/-3.0) and the 74.0 downgrade threshold are FEAT-007's mechanic — they survive the formula change. Only the state classification logic that produces STRONG/WEAK changes. |
| **Implementation impact** | The `apply_regime_score_modifier` equivalent for FEAT-007 receives the state from the difference-formula classifier, not the ratio-formula classifier. The score delta values and downgrade logic are identical. |

### Mismatch 4 — Section 9.4: Deterministic constraints reference ratio

| Field | Value |
|-------|-------|
| **Section** | §9.4 Deterministic constraints (line 186) |
| **Current wording** | "a ratio of exactly 0.90 is `NEUTRAL` (not WEAK); exactly 1.10 is `NEUTRAL` (not STRONG)" |
| **Required wording** | "a difference of exactly 0.0 is `STRENGTH` (not WEAK)" — matching SR-003's `is_underperforming = sector_rs_20 < 0` (strictly less than zero). The boundary-conservatism principle survives but the boundary value changes from 0.90/1.10 to 0.0. |
| **Why it changes** | The ratio thresholds (0.90/1.10) do not exist in the difference formula. The boundary rule must be restated on the difference scale. |
| **Implementation impact** | The boundary test case changes from `ratio=0.90` → NEUTRAL to `difference=0.0` → STRENGTH (not WEAK). |

### Mismatch 5 — Section 9.5: Worked numeric examples use ratio values

| Field | Value |
|-------|-------|
| **Section** | §9.5 Worked numeric examples (lines 190-198) |
| **Current wording** | Table uses `ratio` column with values like 1.25, 0.80, None. Example: "Pre=80.0, BUY, ratio=1.25, STRONG, +1.5, 81.5, BUY" |
| **Required wording** | Table must use `sector_rs_value` column with values in percentage points. Example: "Pre=80.0, BUY, rs_value=+5.2, STRENGTH, +1.5, 81.5, BUY" and "Pre=76.0, BUY, rs_value=-3.1, WEAK, -3.0, 73.0, WATCH" |
| **Why it changes** | The worked examples are the implementation reference. They must use the canonical formula's output scale. |
| **Implementation impact** | Unit test inputs (§15.2) must be rewritten to use difference-scale values instead of ratio values. |

### Mismatch 6 — Section 10: Dependency on `compute_sector_strength` (ratio helper)

| Field | Value |
|-------|-------|
| **Section** | §10 Required Inputs (lines 204-210) and §8 (line 140) |
| **Current wording** | "FEAT-007 does not fetch any data itself. It consumes the values FEAT-004's `SectorStrengthHelper` already produces (FEAT-004 §2.5, §4 data contract)." Inputs listed: `sector_roc20`, `benchmark_roc20`, `relative_strength_ratio`. |
| **Required wording** | "FEAT-007 does not fetch any data itself. It consumes the values produced by the canonical difference-formula sector RS computation (SR-003 `SectorRelativeStrengthService` or a revised shared helper)." Inputs listed: `sector_roc20`, `benchmark_roc20` (or `nifty50_roc20`), `sector_rs_value` (difference). The dependency on `compute_sector_strength`'s ratio outputs is **severed** per ADR-003 §8.5. |
| **Why it changes** | ADR-003 §8.5: "remove the duplicate (`compute_sector_strength` or SR-003) so only one sector-RS path survives." ADR-003 §0 retains SR-003 as the reference implementation. `compute_sector_strength` uses the rejected ratio formula and must either be removed or revised to the difference formula. |
| **Implementation impact** | FEAT-007 must consume SR-003's `sector_rs_20` field (difference), not `compute_sector_strength`'s `relative_strength_ratio` field (ratio). The data plumbing changes from FEAT-004's `compute_sector_strength` path to SR-003's `SectorRelativeStrengthService` path (or a new shared helper that wraps the difference formula). |

### Mismatch 7 — Section 11.2: Log payload field name

| Field | Value |
|-------|-------|
| **Section** | §11.2 Log payload (line 231) |
| **Current wording** | `sector_relative_strength_ratio = float \| null` |
| **Required wording** | `sector_rs_value = float \| null` (the difference value in percentage points) |
| **Why it changes** | The log field must reflect the canonical formula's output, not the rejected ratio. |
| **Implementation impact** | The log payload schema changes one field name. Monitoring tooling that consumes this field must be updated. The field shape (float|null) is unchanged. |

### Mismatch 8 — Section 11.3: Human-readable explanation string

| Field | Value |
|-------|-------|
| **Section** | §11.3 Human-readable explanation (lines 244-246) |
| **Current wording** | `"Sector: IT — STRONG vs Nifty 500 (ratio 1.25, sector ROC20 +4.8% vs benchmark +3.8%). Score adjusted by +1.5 (79.0 → 80.5)."` |
| **Required wording** | `"Sector: IT — STRENGTH vs Nifty 500 (RS +1.0 pp, sector ROC20 +4.8% vs benchmark +3.8%). Score adjusted by +1.5 (79.0 → 80.5)."` |
| **Why it changes** | The explanation must display the difference value ("+1.0 pp") not the ratio ("1.25"). |
| **Implementation impact** | The explanation string template changes from `ratio {value}` to `RS {value} pp`. |

### Mismatch 9 — Section 12: Safe-fallback for `benchmark_roc20 == 0`

| Field | Value |
|-------|-------|
| **Section** | §12 Safe Fallback Behavior (line 258) |
| **Current wording** | "`benchmark_roc20 == 0` (safe-divide) → ratio set to 1.0 → `NEUTRAL`; zero delta" |
| **Required wording** | This fallback is **eliminated**. The difference formula is well-defined when `benchmark_roc20 == 0`: `sector_rs_value = sector_roc20 - 0.0 = sector_roc20`. No safe-divide is needed. The row should be removed or replaced with: "`benchmark_roc20 == 0`: difference formula evaluates normally (`sector_rs_value = sector_roc20`); no special handling required." |
| **Why it changes** | ADR-003 §4.1: "Well-defined at all benchmark values (no division-by-zero edge)." The ratio's safe-fallback was a workaround for a pathology that does not exist in the difference formula. |
| **Implementation impact** | The `benchmark_roc20 == 0` special case is removed from the implementation. One fewer branch to test. |

### Mismatch 10 — Section 15.2: Unit test plan inputs use ratio values

| Field | Value |
|-------|-------|
| **Section** | §15.2 Unit test plan (lines 315-330) |
| **Current wording** | Tests use `ratio=1.25`, `ratio=0.80`, `ratio=1.00`, `ratio=None`, `ratio=0.90`, `ratio=1.10`, `benchmark_roc20=0` |
| **Required wording** | Tests must use difference-scale values: `rs_value=+5.0` (STRENGTH), `rs_value=-3.0` (WEAK), `rs_value=0.0` (boundary), `rs_value=None` (UNKNOWN). The test for `benchmark_roc20=0 → ratio=1.0` is removed (no safe-divide in the difference formula). The boundary tests change from `ratio=0.90` / `ratio=1.10` to `rs_value=0.0` (boundary between WEAK and STRENGTH). |
| **Why it changes** | Test inputs must match the canonical formula's scale. |
| **Implementation impact** | All 14 unit test cases must be rewritten with difference-scale inputs. The test structure (14 cases) is preserved; only the input values and expected state classifications change. |

### Mismatch 11 — Section 17: Final recommendation references ratio computation

| Field | Value |
|-------|-------|
| **Section** | §17 Final Recommendation (line 382) |
| **Current wording** | "It reuses FEAT-004's `SectorStrengthHelper`, sector mapping, benchmark OHLCV, and `relative_strength_ratio` computation without modification." |
| **Required wording** | "It reuses the canonical difference-formula sector RS computation (per ADR-003), sector mapping, and benchmark OHLCV. The formula is `sector_rs_value = sector_roc20 − benchmark_roc20` (percentage points)." |
| **Why it changes** | The dependency on `compute_sector_strength`'s ratio computation is severed by ADR-003. |
| **Implementation impact** | None (documentation only — the implementation impact is captured in Mismatch 6). |

### Mismatch 12 — Candidate Idea Submission table (line 21-22)

| Field | Value |
|-------|-------|
| **Section** | Candidate Idea Submission (lines 21-22) |
| **Current wording** | "the relative-strength ratio, state, score delta, and downgrade decision are always identical" and "A human can read the logged `sector_regime_state`, `sector_relative_strength_ratio`, `sector_roc20`, and `benchmark_roc20` fields" |
| **Required wording** | "the sector RS value (difference), state, score delta, and downgrade decision are always identical" and "A human can read the logged `sector_regime_state`, `sector_rs_value`, `sector_roc20`, and `benchmark_roc20` fields" |
| **Why it changes** | The field name changes from `sector_relative_strength_ratio` to `sector_rs_value`. |
| **Implementation impact** | None (documentation only). |

### Mismatch 13 — Section 2: One-line summary (line 37)

| Field | Value |
|-------|-------|
| **Section** | §2 One-Line Summary (line 37) |
| **Current wording** | "Compute each stock's sector index relative strength versus the benchmark (Nifty 500)" — this is formula-agnostic and does not need changing. |
| **Required wording** | No change needed — the summary does not mention "ratio." ✅ |
| **Why it changes** | N/A |
| **Implementation impact** | None |

---

## 3. Production Files That Will Require Code Changes

### Files that MUST change for FEAT-007 implementation

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `backend/app/services/sector_rs_service.py` | **Upgrade mechanic**: add score deltas (+1.5/-3.0), STRONG cap, REJECT immutability, 74.0 downgrade threshold, pre-Gate placement. The formula (difference) is already correct — no formula change needed. | ADR-003 retains SR-003 as the reference implementation. FEAT-007's mechanic upgrades are applied here. |
| 2 | `backend/app/agents/orchestrator_agent.py` | **Move SR-003 call** from post-Gate (challenger, line 698-727) to pre-Gate (composite, before line 594). Pass `sector_rs_value` to the recommendation agent. Add `feat007` config and enable/disable flag. | FEAT-007 spec §9.3 requires pre-Gate placement. The orchestrator currently applies SR-003 post-Gate as a challenger modifier. |
| 3 | `backend/app/config/settings.py` | **Add `feat007` config section**: `feat007_enabled=False`, `feat007_stage="SHADOW"`, score deltas, downgrade threshold, STRONG cap settings. | No FEAT-007 config exists. |
| 4 | `backend/app/agents/recommendation_agent.py` | **Add FEAT-007 kwargs** to `run()` signature (or consume them inside `RecommendationService.build()`). | FEAT-007 must hook into the recommendation pipeline to apply the score modifier. |
| 5 | `backend/app/services/recommendation_service.py` | **Add FEAT-007 overlay hook** after the FEAT-004 overlay (line ~108) and before the Strict Buy Gate. Call the sector RS modifier. | The overlay must fire between FEAT-004 and the gate, per spec §9.3. |
| 6 | `backend/app/schemas/analysis.py` | **Add FEAT-007 fields** to `SectorOverlayResult` or create a new `Feat007LogPayload` schema. Add `feat007` dynamic attribute support to `FinalRecommendation`. | The log payload schema must be formalized. |

### Files that SHOULD change (dead code cleanup per ADR-003 §8.5)

| # | File | Change | Why |
|---|------|--------|-----|
| 7 | `backend/app/services/feat004_regime_overlay.py` | **Revise or remove `compute_sector_strength`** (lines 305-403). If retained, replace the ratio formula (line 381: `sector_roc20 / bm_roc`) with the difference formula (`sector_roc20 - bm_roc`). Update the classification thresholds from ratio (1.10/0.90) to difference (0.0 or proposed ±X pp). Update the log payload field from `sector_relative_strength_ratio` to `sector_rs_value`. | ADR-003 §8.5: "remove the duplicate so only one sector-RS path survives." `compute_sector_strength` uses the rejected ratio formula. |

### Files that must NOT change

| File | Reason |
|------|--------|
| `backend/app/services/backtest_service.py` | FEAT-008 scope. Complete. |
| `backend/app/services/market_permission_service.py` | SR-004 scope. Unrelated. |
| `backend/app/services/feat004_regime_overlay.py` (non-sector parts) | FEAT-004 core overlay (regime classification, score modifier) is complete and wired. Only `compute_sector_strength` needs revision. |
| `backend/app/agents/backtest_agent.py` | FEAT-008 scope. |
| `backend/app/agents/technical_analysis_agent.py` | Unrelated. |
| `backend/app/agents/news_analysis_agent.py` | Unrelated. |
| `backend/app/agents/fundamental_analysis_agent.py` | Unrelated. |
| `backend/app/agents/ranking_agent.py` | Unrelated. |
| `backend/app/tests/test_backtest_realism.py` | FEAT-008 scope. Complete. |
| `backend/app/tests/test_feat004_regime_overlay.py` | FEAT-004 scope. Complete (unless `compute_sector_strength` tests need updating after the ratio→difference revision). |

### Files that may need test updates

| # | File | Change | Why |
|---|------|--------|-----|
| 8 | `backend/app/tests/test_sector_rs_overlay.py` | **Update tests** to verify the new mechanic (score deltas, pre-Gate placement, STRONG cap, REJECT immutability). Existing tests verify the old post-Gate binary mechanic. | The SR-003 upgrade changes behavior that existing tests assert. |
| 9 | New file: `backend/app/tests/test_feat007_sector_overlay.py` | **Create FEAT-007 test suite**: 14 unit tests per spec §15.2 (rewritten for difference-scale inputs) + cross-feature abstention test + integration tests. | FEAT-007 requires its own test suite matching the spec's test plan. |

---

## 4. Current Recommendation Flow (Integration Context)

```
[OHLCV pre-fetch] → [Bulk Technical Analysis]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Concurrent: BacktestAgent + NewsAgent + FundamentalAgent    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ RecommendationService.build()                               │
│   ├── Composite score (weighted dynamic sum)                │
│   ├── [FEAT-004 Overlay] ← ACTIVE (wired in Batch 2)       │
│   ├── [FEAT-007 Overlay] ← NOT YET IMPLEMENTED             │
│   └── FinalRecommendation                                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ _enforce_strict_buy_gate()                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SR-003 Sector Overlay (POST-Gate) ← CURRENT PLACEMENT       │
│   SectorRelativeStrengthService.evaluate_sector_overlay()    │
│   Binary WEAK/STRENGTH, challenger downgrade                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SR-004 Market Permission (POST-Gate)                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
  StockAnalysisResult
```

**FEAT-007 integration target:** Move the sector RS overlay from POST-Gate (current SR-003 placement) to PRE-Gate (inside `RecommendationService.build()`, after FEAT-004, before the Strict Buy Gate). The overlay changes from a binary challenger downgrade to a continuous score modifier with the difference formula.

---

## 5. Existing Configuration

### What exists

```python
# settings.py — FEAT-004 config (complete, Batch 1+2)
feat004_enabled: bool = False
feat004_stage: str = "SHADOW"
feat004_sector_mapping_enabled: bool = False
# ... (16 fields total)

# settings.py — FEAT-008 config (complete)
feat008_enabled: bool = True
feat008_execution_model: str = "REALISTIC"
# ... (4 fields total)
```

### What is needed for FEAT-007

```python
# settings.py — FEAT-007 config (to be added)
feat007_enabled: bool = False              # Master switch
feat007_stage: str = "SHADOW"              # SHADOW | ACTIVE
feat007_score_delta_strong: float = 1.5    # STRENGTH bonus
feat007_score_delta_weak: float = -3.0     # WEAK penalty
feat007_buy_downgrade_threshold: float = 74.0  # BUY→WATCH if below
feat007_strong_cap_below_buy: bool = True  # Prevent WATCH→BUY
feat007_neutral_band: float = 0.0          # Difference threshold for WEAK (< 0)
```

---

## 6. Existing Helper Functions

### SR-003 — `sector_rs_service.py` (192 lines, LIVE)

| Function | Lines | Purpose | Formula |
|----------|-------|---------|---------|
| `evaluate_sector_overlay()` | 65-192 | Fetch sector + benchmark OHLCV, compute ROC20, compute `sector_rs_20`, classify WEAK/STRENGTH, set `downgrade_triggered` | Difference ✅ |
| `_to_ist_trading_date()` | 28-63 | Normalize timestamps to IST trading dates | N/A |

**Key computation (lines 166-168):**
```python
roc20_sector = ((sector_close_t / sector_close_t_minus_20) - 1) * 100
roc20_nifty50 = ((nifty50_close_t / nifty50_close_t_minus_20) - 1) * 100
sector_rs_20 = roc20_sector - roc20_nifty50
```

**Classification (lines 178-186):**
```python
is_downtrend = sector_close_t < sector_ema20_t
is_underperforming = sector_rs_20 < 0
if is_downtrend and is_underperforming:
    result.sector_filter_status = "WEAK"
    result.downgrade_triggered = True
else:
    result.sector_filter_status = "STRENGTH"
```

**Note:** SR-003 uses `NIFTY50-INDEX` as the benchmark (hardcoded, line 99). The FEAT-007 spec prefers `NIFTY500` with `NIFTY50` fallback. This benchmark difference is a secondary concern — the formula is the same regardless of benchmark.

### `compute_sector_strength` — `feat004_regime_overlay.py` (DEAD)

| Function | Lines | Purpose | Formula |
|----------|-------|---------|---------|
| `compute_sector_strength()` | 305-403 | Compute sector RS as metadata-only (v1 contract: MUST NOT change score) | Ratio ❌ |

**Key computation (line 381):**
```python
relative_strength_ratio = round(sector_roc20 / bm_roc, 4)
```

**Classification (lines 384-389):**
```python
if relative_strength_ratio > 1.10:
    sector_regime_state = "STRONG"
elif relative_strength_ratio >= 0.90:
    sector_regime_state = "NEUTRAL"
else:
    sector_regime_state = "WEAK"
```

**This function must be revised or removed** per ADR-003 §8.5.

---

## 7. Existing Tests

### `test_sector_rs_overlay.py` (358 lines)

| Test | Lines | What it verifies |
|------|-------|-----------------|
| `test_sector_rs_evaluation_weak_sector` | 42-88 | WEAK classification on declining + underperforming sector |
| `test_sector_rs_evaluation_strong_sector` | 90-133 | STRENGTH classification on healthy sector |
| `test_sector_rs_evaluation_insufficient_history` | 135-169 | INSUFFICIENT_HISTORY on missing/short data |
| `test_sector_rs_evaluation_unmapped` | 171-192 | UNMAPPED when symbol not in sector mapping |
| (DB persistence test) | 220-257 | `AnalysisHistory` persistence of `sector_rs_20`, `sector_filter_triggered` |
| (orchestrator integration test) | 265-352 | Full overlay evaluation through the service |

**These tests verify the CURRENT mechanic (post-Gate, binary, challenger downgrade).** They will need updating when the mechanic is upgraded to pre-Gate, three-state (or binary with score deltas), and composite modifier.

### FEAT-007 test suite — **does not exist yet**

The spec §15.2 defines 14 unit tests. These must be created with difference-scale inputs.

---

## 8. Existing Logging

### SR-003 logging

`sector_rs_service.py` logs at:
- `logger.info("Loaded %d sector symbol mappings...")` — startup
- `logger.warning("Warmup indicators contain NaN...")` — data quality
- `logger.error("Error evaluating sector overlay: %s")` — exception boundary

### Orchestrator logging (SR-003 integration)

`orchestrator_agent.py` logs at:
- Line 727: `f"Downgraded to WATCH because mapped sector {sector_overlay.mapped_sector} is weak vs NIFTY 50 (RS: {sector_overlay.sector_rs_20:.2f}%)."` — downgrade message
- Line 683-691: `"Completed symbol analysis"` — includes `recommendation.action`, `confidence`, `score`, `challenger`, `market_regime`

### FEAT-007 logging — **not yet implemented**

The spec §11.2 defines a 12-field log payload. This must be implemented as part of the FEAT-007 overlay.

---

## 9. Existing Feature Flags

| Flag | Location | Default | Status |
|------|----------|---------|--------|
| `feat008_enabled` | `settings.py:115` | `True` | Active |
| `feat004_enabled` | `settings.py:126` | `False` | Wired (Batch 2), disabled |
| `feat007_enabled` | **does not exist** | — | **Not implemented** |
| SR-003 | No flag — always active | — | Live, no config gate |

**Note:** SR-003 currently has no feature flag — it always runs. FEAT-007 implementation must add `feat007_enabled` and gate the new mechanic behind it, with the old SR-003 path as the fallback when disabled.

---

## 10. Runtime Dependencies

| Dependency | Source | Used by | Status |
|------------|--------|---------|--------|
| Sector mapping JSON | `backend/app/config/sector_mappings.json` | SR-003, `compute_sector_strength` | Exists (~80 entries, 10 sectors) |
| NIFTY50 OHLCV | `FyersService` | SR-003 | Live |
| NIFTY500 OHLCV | `FyersService` | FEAT-004 benchmark fetch (wired) | Available |
| Sector index OHLCV | `FyersService` | SR-003, `compute_sector_strength` | Live (via `MarketDataService`) |
| `SectorOverlayResult` schema | `schemas/analysis.py:170-181` | SR-003 | Exists (may need extension for FEAT-007 fields) |
| `AnalysisHistory` model | `models/analysis.py` | Persistence | Has `sector_rs_20`, `sector_filter_triggered` columns |

---

## 11. Potential Regression Risks

| Risk | Severity | Description | Mitigation |
|------|----------|-------------|------------|
| **Placement change breaks Gate** | HIGH | Moving SR-003 from post-Gate to pre-Gate changes which score the Strict Buy Gate sees. Stocks that previously passed the gate might now fail (or vice versa). | Shadow mode for 30+ sessions. Compare pre-Gate vs post-Gate recommendation distributions. Gate reads `raw_technical_score`, not composite — verify this invariant holds. |
| **Score delta changes recommendation distribution** | HIGH | Adding +1.5/-3.0 to composite scores will shift some BUY/WATCH/REJECT boundaries. | Shadow mode monitoring. Compare action distribution before/after. |
| **SR-003 removal breaks persistence** | MEDIUM | `AnalysisHistory` columns `sector_rs_20`, `sector_filter_triggered` are populated by the current SR-003 path. If FEAT-007 replaces SR-003, the persistence path must be preserved. | Ensure FEAT-007's overlay populates the same DB columns, or the orchestrator's persistence code is updated. |
| **FEAT-004 + FEAT-007 double-penalty** | MEDIUM | Both overlays can apply negative deltas simultaneously (FEAT-004 CAUTIOUS -3.0 + FEAT-007 WEAK -3.0 = -6.0 total). | Document the combined effect. Monitor during shadow. The spec §14 already flags this as a known risk. |
| **Benchmark mismatch (NIFTY50 vs NIFTY500)** | LOW | SR-003 uses NIFTY50 (hardcoded). FEAT-004/FEAT-007 spec prefers NIFTY500. If FEAT-007 switches to NIFTY500, classifications may shift. | Make benchmark configurable. Shadow both and compare. |
| **`compute_sector_strength` removal** | LOW | If `compute_sector_strength` is removed from `feat004_regime_overlay.py`, the FEAT-004 log payload (which includes sector metadata) loses its sector fields. | Either revise `compute_sector_strength` to use the difference formula, or have FEAT-007 provide the sector metadata to FEAT-004's log. |
| **Existing SR-003 tests break** | MEDIUM | `test_sector_rs_overlay.py` asserts the current binary post-Gate behavior. Changing the mechanic will break these tests. | Update tests as part of the implementation. Create new FEAT-007 test suite. |

---

## 12. Missing Prerequisites

| Blocker | Description | Resolution |
|---------|-------------|------------|
| **B1: FEAT-007 spec not revised** | The spec still specifies the ratio formula. ADR-003 mandates a v1.1 revision. Implementation cannot proceed against a stale spec. | Revise FEAT-007 spec to v1.1 (formula + thresholds + dependency + log field + worked examples + unit test inputs). This is a documentation prerequisite. |
| **B2: System Owner decision on three-state vs binary** | ADR-003 defers the mechanic upgrade (three-state STRONG/NEUTRAL/WEAK vs binary WEAK/STRENGTH) to a "separate, evidence-backed step." The v1.1 revision must choose. | GOVERNANCE_CONSISTENCY_REVIEW §5.4 recommends binary for v1.1 (minimal change). System Owner must confirm. |
| **B3: Placement conflict unresolved** | SR-003 acts post-Gate as a challenger; FEAT-007 spec acts pre-Gate on the composite. This is a structural change that affects which score the Gate sees. | IMPLEMENTATION_MASTER_PLAN Task 3.2 flags this. Recommendation: align to spec (pre-Gate) to match FEAT-004's pattern. System Owner must confirm. |
| **B4: `compute_sector_strength` formula conflict** | FEAT-004's `compute_sector_strength` uses the rejected ratio formula. If FEAT-007 consumes its outputs, the formula conflict persists in the data path. | Either revise `compute_sector_strength` to the difference formula, or have FEAT-007 consume SR-003's outputs directly. |

---

## 13. Recommended Implementation Order

### Phase 0: Governance (prerequisite — no code)

| Step | Task | Owner | Effort |
|------|------|-------|--------|
| 0.1 | Revise FEAT-007 spec to v1.1 (ratio → difference throughout) | Spec owner | Small |
| 0.2 | System Owner decision: binary (v1.1) vs three-state (deferred) | System Owner | Decision |
| 0.3 | System Owner decision: pre-Gate (spec) vs post-Gate (SR-003) placement | System Owner | Decision |

### Phase 1: Infrastructure (non-disruptive)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 1.1 | Add `feat007` config section to `settings.py` with `enabled=False` | `settings.py` | Small | None |
| 1.2 | Revise `compute_sector_strength` in `feat004_regime_overlay.py` to use the difference formula (or remove it and have FEAT-007 consume SR-003 directly) | `feat004_regime_overlay.py` | Small | Low |
| 1.3 | Extend `SectorOverlayResult` schema with FEAT-007 fields (score delta, adjusted score, log payload) | `schemas/analysis.py` | Small | None |

### Phase 2: Mechanic Upgrade (SR-003 → FEAT-007)

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 2.1 | Add FEAT-007 score modifier to `sector_rs_service.py` (or a new `feat007_sector_overlay.py`): apply +1.5/-3.0 deltas, STRONG cap (71.99), REJECT immutability, 74.0 downgrade threshold | `sector_rs_service.py` or new file | Medium | Low |
| 2.2 | Add FEAT-007 kwargs to `RecommendationAgent.run()` and `RecommendationService.build()` | `recommendation_agent.py`, `recommendation_service.py` | Small | None |
| 2.3 | Add FEAT-007 overlay hook in `RecommendationService.build()` after FEAT-004, before Strict Buy Gate | `recommendation_service.py` | Small | Low |
| 2.4 | Wire orchestrator to pass FEAT-007 config and sector data to the recommendation agent | `orchestrator_agent.py` | Medium | Medium |
| 2.5 | Gate the old SR-003 post-Gate path behind `feat007_enabled` — when FEAT-007 is enabled, use the pre-Gate path; when disabled, fall back to SR-003 | `orchestrator_agent.py` | Medium | Medium |

### Phase 3: Tests

| Step | Task | Files | Effort | Risk |
|------|------|-------|--------|------|
| 3.1 | Create FEAT-007 test suite (14 unit tests with difference-scale inputs + cross-feature abstention test) | New: `test_feat007_sector_overlay.py` | Medium | None |
| 3.2 | Update existing SR-003 tests to handle the new mechanic (or mark as legacy if `feat007_enabled=False` preserves old behavior) | `test_sector_rs_overlay.py` | Medium | Low |
| 3.3 | Add integration tests: FEAT-004 + FEAT-007 combined, disabled byte-identical, shadow passthrough | `test_feat007_sector_overlay.py` | Medium | None |

### Phase 4: Shadow Deployment

| Step | Task | Effort | Risk |
|------|------|--------|------|
| 4.1 | Deploy with `feat007_enabled=True`, `feat007_stage=SHADOW` | Config only | Low |
| 4.2 | Monitor for 30+ sessions | Observability | Ongoing |
| 4.3 | Verify sector RS state distribution (STRENGTH/WEAK/UNKNOWN) | Review | Medium |
| 4.4 | Verify no regression in recommendation distribution vs baseline | Review | Medium |

### Phase 5: Activation

| Step | Task | Effort | Risk |
|------|------|--------|------|
| 5.1 | System Owner approval gate | Decision | N/A |
| 5.2 | Deploy with `feat007_stage=ACTIVE` | Config only | High |
| 5.3 | Monitor recommendation distribution for 5+ sessions | Observability | Ongoing |
| 5.4 | Rollback to SHADOW if metrics degrade | Config only | N/A |

---

## 14. Key Architectural Decisions Already Made (Do NOT Reconsider)

| Decision | Source | Status |
|----------|--------|--------|
| Difference formula is canonical | ADR-003 §0 | **Accepted** |
| Ratio formula is rejected | ADR-003 §11.1 | **Accepted** |
| SR-003 is the reference implementation | ADR-003 §0 | **Accepted** |
| Score deltas (+1.5/-3.0) are FEAT-007's mechanic | FEAT-007 spec §9.3 | **Retained** (ADR-003 scopes formula only) |
| Pre-Gate placement is FEAT-007's design | FEAT-007 spec §9.3 | **Retained** (pending System Owner confirmation on placement) |
| STRONG cap, REJECT immutability, UNKNOWN no-op | FEAT-007 spec §9.4 | **Retained** |
| `compute_sector_strength` must be removed or revised | ADR-003 §8.5 | **Accepted** |

---

## 15. Summary

The FEAT-007 specification (v1.0) contains **12 substantive mismatches** with ADR-003's accepted decision. Every reference to the ratio formula, ratio thresholds (1.10/0.90), the safe-divide fallback, the `relative_strength_ratio` field name, and the dependency on `compute_sector_strength` must be revised to use the difference formula.

The live SR-003 code (`sector_rs_service.py`) already uses the correct difference formula. The implementation work is primarily a **mechanic upgrade** (binary → score deltas, post-Gate → pre-Gate) and **wiring** (config, orchestrator, recommendation service), not a formula change.

**6 production files** require code changes, **1 dead helper** needs revision or removal, **1 existing test file** needs updates, and **1 new test file** must be created.

**4 blockers** must be resolved before implementation begins: the spec revision (B1), the binary-vs-three-state decision (B2), the placement decision (B3), and the `compute_sector_strength` formula conflict (B4).

---

*End of FEAT-007 Synchronization Report*
