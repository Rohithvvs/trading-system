# ADR-002 — Market Regime Consolidation

**Status:** Proposed — awaiting System Owner decision
**Date:** 2026-07-11
**Decides:** The relationship between three market-regime implementations: the live SR-004 (`MarketPermissionService`), the complete-but-dead FEAT-004 module (`feat004_regime_overlay`), and the FEAT-004 specification
**Supersedes:** None
**Blocks:** IMPLEMENTATION_MASTER_PLAN Phase 2

---

## 1. Context

The codebase currently contains **two** market-regime classifiers that both downgrade `BUY → WATCH`, plus a specification (FEAT-004) describing a third. The IMPLEMENTATION_MASTER_PLAN flagged this as Decision D2 and the highest-impact unresolved question in the entire program. Running two regime classifiers in parallel double-counts broad-market weakness; ignoring either wastes working, tested code. This ADR decides which implementation(s) survive and how they relate.

The decision is high-impact because market-regime gating affects *every* recommendation, and the two live paths use different vocabularies, different inputs, and different downgrade thresholds — a correctness and explainability hazard.

---

## 2. Existing Implementation

### 2.1 SR-004 — `MarketPermissionService` (LIVE)

File: `backend/app/services/market_permission_service.py`. Invoked at `orchestrator_agent.py:603`; downgrade applied at `orchestrator_agent.py:622–630`.

**Three independent input signals:**
1. **NIFTY 50 trend** — `close vs EMA50` on `"NIFTY50-INDEX"`. `BULLISH` if `close > ema50`, else `BEARISH`.
2. **India VIX volatility** — `"INDIAVIX-INDEX"` close. States: `NORMAL <18`, `ELEVATED <22`, `HIGH <30`, `EXTREME >=30`.
3. **Breadth proxy** — from `settings.fyers_screener_symbols`; for each, checks `close > ema50`; `breadth_pct = above_count / valid_count`. States: `HEALTHY >=0.50`, `MIXED >=0.30`, `WEAK <0.30`, `UNKNOWN` if <50 % of symbols returned data.

**Four classification states** (top-to-bottom):
- `DEFENSIVE` — VIX EXTREME OR NIFTY missing OR NIFTY stale (>5 days). `new_entry_allowed=False`, `risk_multiplier=0.0`, `manual_review_flag=True`.
- `HIGHRISK` — trend BEARISH OR volatility HIGH OR breadth WEAK. `new_entry_allowed=False`, `risk_multiplier=0.0`.
- `CAUTIOUS` — any component UNKNOWN OR volatility ELEVATED OR breadth MIXED. `new_entry_allowed=True`, `risk_multiplier=0.5`.
- `FAVORABLE` — else (BULLISH AND low VIX AND HEALTHY breadth AND all data present). `new_entry_allowed=True`, `risk_multiplier=1.0`.

**Downgrade mechanic:** the service returns flags; the orchestrator enforces: `if challenger_action == "BUY" and not new_entry_allowed: challenger_action = "WATCH"; challenger_score = min(challenger_score, 71.0)`.

**Safe-fallback:** NIFTY missing → DEFENSIVE immediately. Unhandled exception → HIGHRISK, `new_entry_allowed=False`. VIX missing degrades only `volatility_state` to UNKNOWN → routes to CAUTIOUS.

**Audit/persistence:** persisted to `AnalysisHistory` columns `market_state`, `market_trend_state`, `market_breadth_state`, `market_volatility_state`, `market_new_entry_allowed`, `market_risk_multiplier`. Note: `risk_multiplier` is persisted but **not read back** to scale anything — it is audit-only.

**Placement:** applied **AFTER** the Strict Buy Gate, on the `challenger_recommendation`, not the base recommendation.

### 2.2 FEAT-004 — `feat004_regime_overlay.py` (COMPLETE BUT DEAD)

File: `backend/app/services/feat004_regime_overlay.py`. Called at `recommendation_service.py:100` but always hits the disabled early-return because `RecommendationAgent.run()` (`recommendation_agent.py:42–50`) never passes `feat004_config` / `benchmark_ohlcv`.

**Inputs (different from SR-004):** four booleans derived from **SMA50 / SMA200 / SMA20-slope / ROC20** on a benchmark index (`NIFTY500` preferred, `NIFTY50` fallback). No VIX. No breadth.

**Five classification states** (`classify_market_regime`):
- `ABS` — indicators None or exception.
- `FAV` — `above_sma50 AND sma50_above_sma200 AND slope_positive AND roc20_positive` (all four).
- `NEU` — SMA cross intact, momentum mixed.
- `DEF` — `NOT above_sma50 AND NOT sma50_above_sma200 AND NOT slope_positive`.
- `CAU` — `NOT above_sma50` or `NOT sma50_above_sma200`.
- Default tie-break → `NEU`.

**Score deltas:** `FAV +2.0, NEU 0.0, CAU −3.0, DEF −5.0, ABS 0.0`. **Downgrade thresholds:** `{CAU: 74.0, DEF: 77.0}` (stricter than SR-004's flat 71.0 cap). FAV bonus capped to `buy_threshold − 0.01`.

**Placement:** applied **INSIDE** `RecommendationService.build()`, on the base composite, **BEFORE** the Strict Buy Gate. This is a structural difference from SR-004.

**Contains `compute_sector_strength`** (a metadata-only sector helper using a *ratio* formula — relevant to ADR-003).

### 2.3 The FEAT-004 specification

Matches `feat004_regime_overlay.py` almost exactly (the module was evidently written from the spec). The spec adds: explicit logging schema, brownfield-safety confirmation, Stage A/B rollout, backtest/walk-forward plan.

---

## 3. Proposed Implementation

Five candidate implementations are evaluated in §11. The headline question: is FEAT-004 (SMA/ROC trend regime, 5 states, score-delta modifier, pre-Gate) and SR-004 (VIX/breadth/EMA50 permission, 4 states, binary new-entry gate, post-Gate) the **same feature done twice**, or **two genuinely different concerns** (trend-regime scoring vs. volatility-permission gating)?

---

## 4. Technical Differences (SR-004 vs FEAT-004)

| Dimension | SR-004 (live) | FEAT-004 (dead/spec) |
| :--- | :--- | :--- |
| **Inputs** | NIFTY50 EMA50 + India VIX + breadth proxy | Benchmark SMA50/SMA200/slope/ROC20 (no VIX, no breadth) |
| **Signal type** | Volatility + breadth + simple trend | Pure trend structure |
| **States** | 4: FAVORABLE / CAUTIOUS / HIGHRISK / DEFENSIVE | 5: FAV / NEU / CAU / DEF / ABS |
| **Vocabulary overlap** | "FAVORABLE"≈"FAV", "DEFENSIVE"="DEF" — but conditions differ | — |
| **Effect** | Binary: `new_entry_allowed` boolean → BUY→WATCH + score cap 71.0 | Continuous: score delta (−3/−5) + threshold-gated downgrade (74/77) |
| **Placement** | Post-Gate, on challenger | Pre-Gate, on base composite |
| **Risk multiplier** | Computed (0.0/0.5/1.0), persisted, **unused** | N/A |
| **Score cap on downgrade** | 71.0 (flat) | 74.0 (CAU) / 77.0 (DEF) — stricter |
| **Benchmark** | NIFTY50 (hardcoded) | NIFTY500 preferred, NIFTY50 fallback (configurable) |
| **Cascade behaviour** | SR-004's guard is `if challenger_action == "BUY"` — so if SR-003 already downgraded, SR-004 is skipped | Would run regardless (pre-Gate, on base) |

**The conceptual distinction:** SR-004 answers *"is it safe to enter the market at all right now?"* (volatility/permission). FEAT-004 answers *"how strong is the broad trend, and should the score reflect it?"* (trend/regime scoring). These are arguably different questions — but in this codebase both currently funnel into the same action (BUY→WATCH), so the distinction is not realized.

---

## 5. Advantages

**Of SR-004 (live):** richer inputs (VIX + breadth); already in production; already audited/persisted; conservative (defaults to CAUTIOUS; VIX failure → CAUTIOUS not FAVORABLE).

**Of FEAT-004 (dead/spec):** continuous score deltas (more nuanced than binary gate); configurable benchmark (NIFTY500); pre-Gate placement (cleaner interaction with the composite); spec-aligned (full documentation, shadow/active lifecycle); FAV bonus can reward strong regimes, not only penalise weak ones.

---

## 6. Disadvantages

**Of SR-004:** `risk_multiplier` computed but unused (dead field); binary effect loses nuance; runs post-Gate on challenger (the Gate never sees its effect); hardcoded NIFTY50.

**Of FEAT-004:** dead code — never been exercised in production; no VIX sensitivity (misses volatility spikes that SMA/ROC lag); requires benchmark OHLCV plumbing that no caller builds.

**Of running both:** double-counting broad-market weakness (a HIGH-VIX HIGHRISK state and a below-SMA50 CAU state often co-occur); conflicting vocabularies confuse explainability; two downgrade thresholds (71.0 vs 74.0/77.0) produce inconsistent caps.

---

## 7. Recommendation

**Option C — Merge with separated responsibilities** (see §11). Formalize the conceptual distinction:
- **SR-004 retained as the permission gate** (post-Gate, binary `new_entry_allowed`), but rename its states to avoid collision (e.g. `PERMIT-FAVORABLE` / `PERMIT-CAUTIOUS` / `PERMIT-HIGHRISK` / `PERMIT-DEFENSIVE`) and either wire up or remove the unused `risk_multiplier`.
- **FEAT-004 wired in as the trend-regime score modifier** (pre-Gate, on the composite), with its SMA/ROC states kept distinct (`FAV`/`NEU`/`CAU`/`DEF`/`ABS`).
- A formal non-overlap document: SR-004 = "volatility/breadth permission"; FEAT-004 = "trend-regime scoring." No state-vocabulary collision; no double-downgrade because they act at different pipeline points (pre-Gate score vs. post-Gate permission).

Rationale: the two implementations genuinely capture different signals (VIX/breadth vs. SMA/ROC trend). Throwing either away loses signal. But they must be formally separated or they collide. The pre-Gate vs. post-Gate placement is the natural seam.

---

## 8. Migration Strategy

1. Resolve this ADR (Option A/B/C/D/E).
2. If merging (C): wire FEAT-004 in pre-Gate (Phase 2 of the master plan); keep SR-004 post-Gate; rename SR-004 states to disambiguate; document the non-overlap boundary.
3. Add FEAT-004 config + benchmark fetch plumbing (Phase 2 tasks 2.2–2.5).
4. Backtest the *combined* effect (FEAT-004 pre-Gate + SR-004 post-Gate) to confirm no runaway double-penalty; set a documented bound on combined penalty.
5. Shadow FEAT-004 (it has never run live); promote evidence C→B per FEAT-005 §9.2 before activation.
6. Decide the fate of SR-004's unused `risk_multiplier` (wire up or remove).

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| Double-counting broad-market weakness if both run unseparated | High (under Options A/D) | High | Option C's formal separation + combined-penalty bound |
| FEAT-004 has never run live — first activation is a cold start | High | Medium | Mandatory shadow ≥30 sessions; evidence promotion C→B gate |
| VIX data gaps degrade SR-004 to CAUTIOUS, which could interact with FEAT-004's CAU | Medium | Medium | Monitor co-occurrence in shadow |
| State-vocabulary collision confuses the audit log / dashboard | Medium | Medium | Rename SR-004 states (Option C) |
| Removing SR-004 (Option B) loses VIX/breadth signal | Medium | High | Prefer Option C unless VIX proven redundant |

---

## 10. Rollback Strategy

- FEAT-004: `feat004.enabled = false` (one line; returns to today's behaviour).
- SR-004: already live; rollback = remove the orchestrator call (or gate behind a flag added for this purpose).
- If the merge (Option C) produces instability: disable FEAT-004 first (reverting to SR-004-only = today's behaviour). SR-004 rollback is independent.

---

## 11. Final Decision Options

### Option A — Keep SR-004 only; discard FEAT-004

Treat FEAT-004 as superseded by SR-004. Delete or archive `feat004_regime_overlay.py`. Close FEAT-004 as "superseded."

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Loses SMA/ROC trend-regime nuance; keeps VIX/breadth |
| Brownfield safety | High — nothing changes |
| Determinism | High |
| Explainability | Medium — single regime path |
| Implementation complexity | Trivial (delete dead code) |
| Regression risk | None |
| Technical debt | Medium — discards a complete spec-aligned module; FEAT-004 spec must be marked superseded |
| Long-term maintainability | Medium — single path, but loses the trend-regime signal |

### Option B — Replace SR-004 with FEAT-004

Wire in FEAT-004; deprecate/remove SR-004. Loses VIX and breadth inputs.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Loses volatility/breadth signal — significant |
| Brownfield safety | **Low** — removes a live feature |
| Determinism | High |
| Explainability | Medium |
| Implementation complexity | Medium — wire FEAT-004 + safely remove SR-004 |
| Regression risk | **High** — removing live VIX gating |
| Technical debt | Low |
| Long-term maintainability | Medium |

### Option C — Merge with separated responsibilities (RECOMMENDED)

Keep both; formalize SR-004 = post-Gate volatility/breadth permission gate; FEAT-004 = pre-Gate trend-regime score modifier. Rename SR-004 states to disambiguate. Document non-overlap.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Highest — retains both signal types, placed at their natural pipeline points |
| Brownfield safety | High — SR-004 unchanged; FEAT-004 added disabled, staged via shadow |
| Determinism | High |
| Explainability | High — *if* states are renamed and the non-overlap is documented; otherwise Medium |
| Implementation complexity | Medium — wiring + renaming + non-overlap doc + combined-penalty tuning |
| Regression risk | Low — SR-004 unchanged; FEAT-004 disabled by default |
| Technical debt | Low — both features gain clear ownership |
| Long-term maintainability | High |

### Option D — Keep both, overlapping (status quo + wire FEAT-004)

Wire FEAT-004 without separating from SR-004. Both downgrade.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Negative — double-counts broad-market weakness |
| Brownfield safety | Medium |
| Determinism | High |
| Explainability | **Low** — two colliding regime vocabularies |
| Implementation complexity | Low |
| Regression risk | **High** — runaway double-penalty |
| Technical debt | High |
| Long-term maintainability | Low |

### Option E — Build a unified regime service that consumes both signal sets

One new classifier taking VIX + breadth + SMA/ROC, producing one state, one effect. Replaces both.

| Criterion | Rating |
| :--- | :--- |
| Recommendation quality | Potentially highest — single coherent model |
| Brownfield safety | **Low** — replaces two live/tested services with a new one |
| Determinism | High |
| Explainability | High — single vocabulary |
| Implementation complexity | **High** — new classifier, new validation, supersedes two features |
| Regression risk | High — both paths change at once |
| Technical debt | Low (after) but high migration cost |
| Long-term maintainability | High (after) |

**Recommended: Option C.** It is the only option that retains both signal types (VIX/breadth and SMA/ROC) while eliminating the collision, and it does so with low regression risk because SR-004 is untouched and FEAT-004 is added disabled-then-shadowed. Option D is explicitly discouraged (double-counting). Option E is the cleanest end-state but the most expensive and risky to reach in one step — it is a better *future* target once Option C has stabilised.

---

*End of ADR-002 — proposed, not final.*
