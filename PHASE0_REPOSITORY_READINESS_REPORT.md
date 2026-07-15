# PHASE-0 Repository Readiness Report
**Document:** PHASE0_REPOSITORY_READINESS_REPORT.md
**Version:** 1.0
**Date:** 2026-07-12
**Author:** Principal Software Architect (audit)
**Status:** Implementation gate — must be satisfied before Phase-1 code begins.
**Scope:** Prerequisites for implementing FEAT-008, FEAT-004, FEAT-007 only.
**Method:** Read-only repository audit. No code generated, no features redesigned, no ADRs/FEAT docs modified. Unverifiable items marked "Needs Verification."

---

## 0. Audit Baseline

| Item | Value |
| :--- | :--- |
| Repo root | `F:\trading system01\trading system` |
| VCS | git; current branch `SAI_CHANDRA` |
| Working tree | **DIRTY** — 12 modified tracked files, ~30 untracked files (incl. the entire feature layer) |
| Backend stack | FastAPI + SQLAlchemy(asyncpg) + Alembic + Pydantic-Settings + FYERS SDK + yfinance + Groq LLM |
| Config system | `.env`-driven `pydantic_settings.BaseSettings` singleton (`backend/app/config/settings.py`, 206 lines) — **no YAML/TOML/JSON app config** |
| Schema manager | Alembic, 24 migrations, startup head-gate enforced |
| CI | GitHub Actions: `tests.yml` (PR + push to `main`), `test_matrix.yml` |
| Deploy | Render (`render.yaml`) |
| Python | 3.11 in CI / 3.12 on Render (mismatch — Needs Verification) |

### Governance state (as stated by System Owner)
- Governance FEAT-001/002/003/005/006: complete.
- Feature specs FEAT-004/007/008: complete.
- ADR-001/002/003: stated **Accepted** (ADR-003 = Option C-Revised).
- Implementation Planning Review: complete. Canonical order FEAT-008 → FEAT-004 → FEAT-007.

> **Needs Verification — ADR acceptance status.** `docs/adr/README.md` states "Each is proposed, not final" and lists ADR-003's recommended option as "Option D." ADR-001 and ADR-002 files self-describe as "Proposed — awaiting System Owner decision." Only ADR-003's own file header reads "Accepted (2026-07-11) — Option C-Revised." The README index appears stale relative to ADR-003. This report proceeds on the System Owner's stated governance (all three accepted) but the file-level discrepancy must be reconciled before Phase-1.

---

## 1. Repository Readiness Summary

| Feature | Code state in repo | Production effect today | Net readiness |
| :--- | :--- | :--- | :--- |
| **FEAT-008** (COMP-BT) | **~85% implemented and LIVE.** Two-pass engine in `backtest_service.py`: Pass-2 realistic next-bar-open fills + full Indian cost stack (brokerage/STT/exchange/SEBI/stamp/GST/DP) + slippage + sizing + retro-fee logic. Composite already scores on realistic `total_return`; `gross_*` persisted but unused. 11-test realism suite exists. | Realistic substrate **already active** in the composite. | **Partial.** Missing: `execution_model` switch, `composite_uses_realistic` flag, `feat008` config section, conservative intrabar stop-before-target ordering, `skip_on_missing_next_bar`, end-of-data `TEMPORARY_ASSUMPTION` edge case, FEAT-008 branding, `test_feat008*`. |
| **FEAT-004** (COMP-REC) | **Module complete + tested, but DEAD/UNWIRED.** `feat004_regime_overlay.py` (741 lines) implements all 7 helpers + 5-state classifier + score deltas (-3/-5/+2) + FAV cap + SHADOW/ACTIVE + sector-strength metadata + full §8 log schema + safe-fallback. 535-line test suite (`test_feat004_regime_overlay.py`). | **Zero** — `RecommendationAgent.run()` never passes `feat004_config`/`benchmark_ohlcv`/`sector_mapping`/`sector_ohlcv_cache`; overlay always early-returns disabled. | **Partial.** Missing: `feat004` config section in `settings.py`, benchmark OHLCV fetch plumbing, live wiring from agent, ADR-002 consolidation with live SR-004. |
| **FEAT-007** (COMP-REC) | **NOT implemented as specified.** No `feat007` module/config/hook/tests anywhere. Live `SectorRelativeStrengthService` (SR-003) exists with the **difference** formula, binary WEAK/STRENGTH, post-Gate, flat cap 71.0. | SR-003 downgrade active post-Gate; no FEAT-007 score-delta mechanic. | **Not ready.** Plus: accepted ADR-003 **requires the FEAT-007 spec to be revised** (ratio -> difference formula), which conflicts with the "do not modify FEAT docs" constraint. |

**One-line verdict:** The repository is *further along than a greenfield Phase-0* but is in an **inconsistent, uncommitted, partially-wired state** that must be reconciled before Phase-1.

---

## 2. Repository Health

### Ready
- Backend application structure (FastAPI app, routers/routes, services, agents, models, db, utils, observability).
- Database layer: async + sync engines, Alembic with 24 migrations, startup head-gate, partition manager, advisory locks.
- Market data layer: FYERS primary + yfinance fallback, `historical_candles` (partitioned), `candle_store`, reconciliation, retention.
- Backtest realism math (Pass-2 next-bar-open + full cost stack) — live and tested.
- Recommendation composite weighted-sum engine with dynamic weights (tech 0.50 / fund 0.25 / backtest 0.25 / news 0.0 standard; catalyst 0.20/0.30/0.20/0.30).
- `raw_technical_score` gate-sentinel isolation preserved in `recommendation_service.py:84`.
- FEAT-004 overlay module + 535-line test suite (spec-aligned, in isolation).
- `sector_mappings.json` static config (80 symbols -> 10 sector indices).
- Live SR-003 sector-RS service (difference formula — ADR-003 canonical reference).
- Live SR-004 market-permission service (VIX + breadth + EMA50, post-Gate).
- Strict Buy Gate in `orchestrator_agent.py:_enforce_strict_buy_gate`.
- Logging: structured logger service, DB logger, scan diagnostics (530 lines), Prometheus metrics.
- Caching/scheduler/locking: Redis, distributed locks, task supervisor, scheduler router.
- Test harness: pytest.ini with markers (unit/integration/live/slow/asyncio/concurrency/soak/recovery), 25 test files in `backend/app/tests`.
- CI: GitHub Actions on PR + push to main.

### Missing
- **`feat004` / `feat007` / `feat008` config sections in `settings.py`** — none of the three feature config blocks exist in the pydantic settings model or `.env`.
- **`execution_model` / `composite_uses_realistic` flags** — zero matches in backend code.
- **FEAT-004 live wiring** — `RecommendationAgent.run()` does not pass overlay inputs; benchmark OHLCV never fetched by any caller.
- **FEAT-007 service, hook, config, tests** — do not exist anywhere.
- **`test_feat008*` and `test_feat007*` test files** — do not exist.
- **Committed feature layer** — the entire feature code/migrations/specs/ADRs/tests are uncommitted (see Section 8/9).
- **Conservative intrabar stop-before-target ordering** in backtest (`conservative_exit_ordering` absent).
- **`skip_on_missing_next_bar`** semantics (end-of-data position force-closed at `close[T]` with `TEMPORARY_ASSUMPTION`).

### Needs Verification
- **ADR-001 / ADR-002 acceptance status** (files say "Proposed"; System Owner says "Accepted").
- **`docs/adr/README.md` currency** (stale relative to ADR-003).
- **FYERS index/sector instrument support** (`NIFTY500`, `NIFTY50`, `NSE:NIFTYIT-INDEX`, etc. fetchable as instruments).
- **`sector_mappings.json` coverage** vs the live universe (80 symbols mapped; universe may be ~500+).
- **Broker/NSE cost schedule** (slippage/brokerage/STT/exchange/GST/stamp/SEBI bps) vs contract note.
- **Frontend forward-compatibility** with new nested `feat004`/`feat007` recommendation keys (strict-schema validation risk).
- **Log storage/rotation capacity** for ~3x per-recommendation payload growth.
- **Python version** (CI 3.11 vs Render 3.12).
- **`db/session.py` duplicated block** (content repeated from ~line 153 — hygiene).

---

## 3. Phase-0 Prerequisites

### Mandatory (block Phase-1)
1. **Commit the working tree.** The feature layer (feat004/sector_rs/market_permission services, realism migrations, ADRs, specs, tests, modified `backtest_service.py`/`recommendation_service.py`/`orchestrator_agent.py`) is uncommitted. Phase-1 must start from a clean, tagged baseline.
2. **Reconcile ADR acceptance status.** Update `docs/adr/README.md` and ADR-001/ADR-002 file headers to match the System Owner's accepted decision, or obtain formal sign-off. Phase-1 (FEAT-008) is gated on ADR-001.
3. **Resolve the ADR-003 vs FEAT-007 spec conflict.** Accepted ADR-003 (Option C-Revised) mandates the **difference** formula and states the FEAT-007 spec *must be revised* to replace the ratio formula. The audit constraint forbids modifying FEAT docs. This conflict must be resolved by the System Owner before FEAT-007 implementation can be scoped.
4. **Add `feat008` config section to `settings.py`** per ADR-001 Option B: `execution_model` (default `REALISTIC`), `composite_uses_realistic` (default `true`), `slippage_bps`, `brokerage_bps`, `statutory_bps`, `conservative_exit_ordering`, `skip_on_missing_next_bar`.
5. **Verify broker/NSE cost schedule** against a contract note; replace placeholder bps with verified figures before any FEAT-008 shadow re-baseline.
6. **Add `feat004` config section to `settings.py`**: `enabled`, `stage`, `benchmark_symbols`, `min_benchmark_candles`, `staleness_limit_days`, `sector_mapping_enabled`, `score_deltas`, `buy_downgrade_thresholds`, `favorable_cap_below_buy`, `buy_threshold`.
7. **Wire FEAT-004 into the live pipeline**: `RecommendationAgent.run()` / `RecommendationService.build()` callers must fetch benchmark OHLCV (NIFTY500->NIFTY50 fallback), load `sector_mappings.json`, build the per-session `sector_ohlcv_cache`, and pass `feat004_config`.
8. **Verify FYERS supports index/sector instruments** (`NIFTY500`, `NIFTY50`, `NSE:NIFTYIT-INDEX`, ...). If not, confirm the yfinance fallback path for index series.
9. **Peer-review `sector_mappings.json`** against NSE sector constituents and verify coverage of the active universe.
10. **Add `test_feat008*`** (15 unit tests per FEAT-008 Section 16.2, esp. `test_legacy_mode_byte_identical`, `test_causality_no_same_bar_fill`, `test_conservative_stop_before_target`) and **`test_feat007*`** (14 tests per FEAT-007 Section 15.2 + cross-feature abstention test).
11. **Verify frontend/API forward-compatibility** with additive nested `feat004`/`feat007` keys before any shadow mode writes the full payload.
12. **Verify log storage/rotation** tolerates ~3x per-recommendation payload growth.

### Recommended
- Add the FEAT-007 overlay hook seam in `recommendation_service.py` between the FEAT-004 call (line 108) and the `final_score` assignment (line 124), even if inert, so the pipeline order `composite -> FEAT-004 -> FEAT-007 -> Strict Buy Gate` is structurally fixed.
- Resolve the end-of-data `TEMPORARY_ASSUMPTION` close-at-`close[T]` edge case in `backtest_service.py:458-498` (residual non-causal fill).
- Consolidate the two route folders (`routes/` vs `routers/`) and clean the duplicated block in `db/session.py`.
- Rename SR-004 states per ADR-002 Option C to avoid vocabulary collision with FEAT-004 (FAV/CAU/DEF).
- Reconcile Python version (CI 3.11 vs Render 3.12).

### Optional
- Add a `feat007` config section placeholder (inert) so Phase-3 only flips flags.
- Author a single shared overlay-log schema validator (FEAT-004 Section 8 and FEAT-007 Section 11.2 mirror each other).

---

## 4. Configuration Readiness

**Mechanism:** `.env` + environment variables -> `pydantic_settings.Settings` singleton (`backend/app/config/settings.py`). **No YAML/JSON app-config driver.** The only JSON config artifact is `backend/app/config/sector_mappings.json` (a data file, not settings).

| Config block | Required by | Exists in `settings.py`? | Status |
| :--- | :--- | :--- | :--- |
| `feat008.execution_model` (LEGACY/REALISTIC) | FEAT-008 | No | **Must add** (ADR-001 Option B: default `REALISTIC`) |
| `feat008.composite_uses_realistic` | FEAT-008 | No | **Must add** (default `true` — composite already uses realistic) |
| `feat008.slippage_bps` / `brokerage_bps` / `statutory_bps` | FEAT-008 | No (costs live in `COST_SCENARIOS` dict inside `backtest_service.py`) | **Must add** as named config; verify figures vs contract note |
| `feat008.conservative_exit_ordering` | FEAT-008 | No | **Must add** |
| `feat008.skip_on_missing_next_bar` | FEAT-008 | No | **Must add** |
| `feat004.enabled` / `.stage` (SHADOW/ACTIVE) | FEAT-004 | No (exists only as in-module dict defaults + test fixture) | **Must add** |
| `feat004.benchmark_symbols` (NIFTY500/NIFTY50) | FEAT-004 | No | **Must add** |
| `feat004.min_benchmark_candles` / `staleness_limit_days` | FEAT-004 | No | **Must add** |
| `feat004.sector_mapping_enabled` | FEAT-004 | No (in-module key only) | **Must add** |
| `feat004.score_deltas` (FAV/NEU/CAU/DEF/ABS) | FEAT-004 | No (defaults in module: 2/0/-3/-5/0) | **Must add** |
| `feat004.buy_downgrade_thresholds` (CAU 74 / DEF 77) | FEAT-004 | No | **Must add** |
| `feat004.favorable_cap_below_buy` / `buy_threshold` | FEAT-004 | No (cap logic present in module) | **Must add** |
| `feat007.enabled` / `.stage` / score deltas (+1.5/-3.0) | FEAT-007 | No | **Must add** (Phase-3; pending spec revision per ADR-003) |
| Sector mapping config (`symbol -> sector_index_symbol`) | FEAT-004/007 | Yes — `sector_mappings.json` (80 symbols, 10 sectors) | Exists; **coverage needs verification** vs universe |
| Logging config | All | Yes — `core/logger.py`, `core/log_manager.py`, `services/logger_service.py`, `services/db_logger.py` | Ready; rotation Needs Verification for 3x growth |
| Cost model (`COST_SCENARIOS`: LOW/BASE/STRESS) | FEAT-008 | Yes — hardcoded in `backtest_service.py:19-56` | Exists; **figures Need Verification** vs contract note |
| Market regime config (SR-004) | FEAT-004 (consolidation) | Yes — embedded in `market_permission_service.py` | Live; ADR-002 requires state rename + boundary doc |

> **Note on ADR-001 vs FEAT-008 spec default:** ADR-001 Option B explicitly warns against defaulting `execution_model = LEGACY` because the composite already runs on realistic `total_return` — flipping to LEGACY default would be a silent production behaviour change. The FEAT-008 spec Section 13 shows `execution_model: "LEGACY"` as the example default. **This is a spec-vs-ADR conflict the System Owner must adjudicate.**

---

## 5. Data Readiness

| Dataset | Required by | Available? | Source / location | Status |
| :--- | :--- | :--- | :--- | :--- |
| Historical daily OHLCV (stocks) | All three | Yes | `historical_candles` table (partitioned); FYERS primary + yfinance fallback via `fyers_service.py`/`market_data_service.py` | Ready |
| Benchmark index OHLCV (NIFTY500/NIFTY50) | FEAT-004/007 | Needs Verification | Same data layer, but **no caller fetches an index series today**. FYERS instrument support for `NIFTY500`/`NIFTY50` unverified. | Fetch path + instrument support must be verified |
| Sector index OHLCV (NIFTYIT, NIFTYBANK, ...) | FEAT-004/007 | Needs Verification | `sector_mappings.json` maps to `NSE:NIFTYIT-INDEX` etc.; FYERS sector-index fetchability unverified | Must verify per sector in universe |
| Sector mapping (`symbol -> sector_index`) | FEAT-004/007 | Yes (partial) | `backend/app/config/sector_mappings.json` (80 symbols, 10 sectors) | **Coverage Needs Verification** vs active universe (~500+) |
| Index mapping (NIFTY universes) | Universe mgmt | Yes | `ind_nifty500list.csv` + `settings.nifty500_symbols`/`universe_symbols` | Ready |
| Brokerage values | FEAT-008 | Yes (hardcoded) | `COST_SCENARIOS` in `backtest_service.py:19-56` (LOW/BASE/STRESS) | **Figures Need Verification** vs contract note |
| Taxes / statutory (STT/exchange/GST/stamp/SEBI) | FEAT-008 | Yes (hardcoded) | `calculate_transaction_costs` `backtest_service.py:58-127` | **Figures Need Verification**; rates change on budgetary schedule |
| Trading costs (slippage) | FEAT-008 | Yes (hardcoded) | `slippage_rate` in `COST_SCENARIOS`; applied at `:341`,`:374` | Needs Verification vs contract note |
| Benchmark availability (NIFTY indices) | FEAT-004/007 | Needs Verification | NIFTY50 used by SR-004 live; NIFTY500 fetch path unverified | Verify |
| Missing datasets | — | — | No **new** datasets required by any feature (all consume existing OHLCV + static config) | None blocking except verification |

---

## 6. Code Readiness

### Existing reusable services
| Service | Path | Reuse for |
| :--- | :--- | :--- |
| `BacktestService` | `backend/app/services/backtest_service.py` | FEAT-008 (in-place: add switch, flag, edge cases) |
| `RecommendationService` | `backend/app/services/recommendation_service.py` | FEAT-004/007 (overlay hook point at lines 99-108 / 124) |
| `feat004_regime_overlay` | `backend/app/services/feat004_regime_overlay.py` | FEAT-004 (already spec-aligned; needs wiring + config) |
| `SectorRelativeStrengthService` (SR-003) | `backend/app/services/sector_rs_service.py` | FEAT-007 reference impl (difference formula per ADR-003) |
| `MarketPermissionService` (SR-004) | `backend/app/services/market_permission_service.py` | ADR-002 consolidation (post-Gate; rename states) |
| `MarketDataService` / `fyers_service` | `backend/app/services/` | Benchmark/sector OHLCV fetch plumbing |
| `PersistenceService` / `LatestScanService` | `backend/app/services/` | Recommendation persistence (larger JSON payloads) |
| `TechnicalAnalysisService` | `backend/app/services/technical_analysis_service.py` | Produces `raw_technical_score` (gate sentinel) |
| `LoggerService` / `ScanDiagnostics` | `backend/app/services/`, `backend/app/observability/` | Structured logging for overlay payloads |

### Existing reusable helpers / utilities
| Helper | Path | Use |
| :--- | :--- | :--- |
| `sanitize_for_json` | `backend/app/utils/json_sanitize.py` | NaN/Inf->0 for overlay log payloads |
| `canonical_symbol` / `fyers_symbol` | `backend/app/utils/symbol.py` | Index symbol resolution (`-INDEX` preserved) |
| `calculate_transaction_costs` | `backtest_service.py:58-127` | FEAT-008 cost model (already Indian-NSE complete) |
| `calculate_dynamic_weights` | `recommendation_service.py:167-191` | Composite weight regimes (backtest 0.25/0.20) |
| advisory locks / `DistributedLockService` | `backend/app/db/locks.py`, `services/lock_service.py` | Concurrency |

### Shared models / abstractions
- `BacktestResult` schema (`schemas/analysis.py`) already carries realism fields: `gross_total_return`, `gross_cagr`, `gross_max_drawdown`, `gross_win_rate`, `gross_profit_factor`, `gross_sharpe_ratio`, `cost_scenario`, `total_transaction_costs`, `total_slippage`, `position_sizing_pct`, `cagr_warning`.
- `AnalysisHistory` / `BacktestHistory` ORM (`models/analysis.py`) already persist gross realism metrics + SR-003/SR-004 audit columns.
- `FinalRecommendation` schema accepts dynamic `feat004` attribute (`recommendation_service.py:161-164`).

### Code that should NOT be modified
- **Strict Buy Gate** (`orchestrator_agent.py:_enforce_strict_buy_gate`) — all three specs mandate it stays unchanged.
- `raw_technical_score` sentinel (`recommendation_service.py:84`) — never mutated by any overlay.
- BUY/WATCH/REJECT thresholds (72/55) — unchanged.
- Composite weight formula and normalization — unchanged (FEAT-008 changes the *input*, not the formula).
- FEAT-001..008 specification documents and ADRs — per audit constraints.

---

## 7. Dependency Readiness

### Per-feature prerequisites
**FEAT-008 prerequisites:**
- ADR-001 decision finalized (Option B: brand + switch default REALISTIC + verify edge cases).
- `feat008` config section in `settings.py`.
- Verified cost schedule (brokerage/STT/exchange/GST/stamp/SEBI/slippage).
- Conservative exit-ordering implementation + `test_conservative_stop_before_target`.
- `skip_on_missing_next_bar` + end-of-data edge case resolution.
- `test_legacy_mode_byte_identical` (note: LEGACY = Pass-1 gross; composite currently uses Pass-2 — byte-identity baseline must be defined against current Pass-2 behaviour, **Needs Verification** given ADR-001).

**FEAT-004 prerequisites:**
- FEAT-008 substrate stabilized (validity dependency — overlays tuned against realistic composite).
- `feat004` config section in `settings.py`.
- Benchmark OHLCV fetch path (NIFTY500->NIFTY50) verified against FYERS.
- `sector_mappings.json` peer-reviewed + coverage verified.
- Live wiring: `RecommendationAgent.run()` -> `RecommendationService.build()` must pass `feat004_config`/`benchmark_ohlcv`/`sector_mapping`/`sector_ohlcv_cache`.
- ADR-002 consolidation: SR-004 state rename + non-overlap boundary documented.
- Frontend forward-compat + log capacity verified (shadow writes full payload).

**FEAT-007 prerequisites:**
- FEAT-004 sector plumbing live (`compute_sector_strength` + sector OHLCV cache + `sector_mappings.json`).
- **ADR-003 spec revision executed** — FEAT-007 spec updated to difference formula (conflicts with "do not modify FEAT docs" — **System Owner decision required**).
- `feat007` service module + hook in `recommendation_service.py` (between line 108 and 124).
- `feat007` config section.
- Three-state STRONG/NEUTRAL/WEAK classification on the **difference** formula (per ADR-003).
- Score deltas (+1.5/-3.0), STRONG cap, REJECT immutability, 74.0 downgrade threshold.
- `test_feat007*` (14 tests + cross-feature FEAT-004-disabled abstention test).

### Dependency graph
```
   +--------------+
   |   FEAT-008   |  (substrate: backtest_score INPUT) - ~85% live; add switch/flag/edge cases
   |  COMP-BT     |  NO code dependency. ADR-001 gates.
   +------+-------+
          |  validity dependency (overlays tuned to stable realistic composite)
          v
   +--------------+
   |   FEAT-004   |  (overlay 1: broad-market regime, composite OUTPUT) - module complete, DEAD; wire + config
   |  COMP-REC    |  ADR-002 gates. Introduces compute_sector_strength + sector plumbing.
   +------+-------+
          |  HARD code dependency: FEAT-007 consumes compute_sector_strength + sector data
          v
   +--------------+
   |   FEAT-007   |  (overlay 2: sector RS, composite OUTPUT after FEAT-004) - NOT implemented; spec revision per ADR-003
   |  COMP-REC    |  ADR-003 gates (Option C-Revised: difference formula canonical).
   +--------------+

   In-pipeline order (target): composite -> FEAT-004 -> FEAT-007 -> Strict Buy Gate
   Today's live order:        composite -> (FEAT-004 disabled) -> Strict Buy Gate -> SR-003 (post-Gate) -> SR-004 (post-Gate)
```

---

## 8. Risk Assessment

### Technical risks
| # | Risk | L | I | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| T1 | FYERS does not support `NIFTY500`/`NIFTY50`/sector indices as fetchable instruments | Med | High | Verify Phase-0; yfinance fallback (FEAT-004 Section 2 allows) |
| T2 | `test_legacy_mode_byte_identical` baseline ambiguous — composite already uses Pass-2 realistic; "LEGACY" = Pass-1 gross which never scored | Med | High | Define baseline per ADR-001 Option B (LEGACY = gross pass) |
| T3 | Log payload ~3x growth overwhelms storage/rotation | Med | Med | Verify Phase-0; add rotation |
| T4 | Frontend strict-schema validation rejects additive `feat004`/`feat007` keys | Med | Med | Verify forward-compat Phase-0 |
| T5 | Conservative exit ordering not present; intrabar stop/target ambiguous | Med | Med | Implement + test `conservative_exit_ordering` |
| T6 | End-of-data `TEMPORARY_ASSUMPTION` close-at-`close[T]` is a residual non-causal fill | Low | Med | Resolve with `skip_on_missing_next_bar` |

### Data risks
| # | Risk | L | I | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| D1 | `sector_mappings.json` maps symbols to wrong sector indices / incomplete coverage | Med | High | Peer-review vs NSE constituents; verify coverage |
| D2 | Cost-schedule figures stale (STT/brokerage rate changed) | Med | Med | Verify vs contract note; config-driven |
| D3 | Benchmark/sector OHLCV stale on holidays -> misclassification | Low | Med | Staleness check (FEAT-004 Section 7) -> ABSTAINED |

### Architecture risks
| # | Risk | L | I | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| A1 | **ADR-003 requires modifying the FEAT-007 spec** (ratio->difference) — conflicts with audit constraint | High | High | System Owner adjudicates: revise spec or revise ADR |
| A2 | ADR-001 default (`REALISTIC`) conflicts with FEAT-008 spec example default (`LEGACY`) | Med | High | System Owner adjudicates; ADR-001 warns LEGACY default = silent production change |
| A3 | FEAT-004 (pre-Gate, trend) and SR-004 (post-Gate, VIX/breadth) vocabulary collision (FAV/CAU/DEF) | Med | Med | ADR-002 Option C: rename SR-004 states |
| A4 | Two parallel route folders (`routes/` vs `routers/`) + duplicated `db/session.py` block | Low | Low | Hygiene cleanup |

### Configuration risks
| # | Risk | L | I | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| C1 | No `feat004/007/008` config sections exist — features cannot be flag-rolled back | High | High | Add all three config sections before any activation |
| C2 | Costs hardcoded in `backtest_service.py` not in settings — not env-overridable | Med | Med | Externalize to `feat008` config |

### Deployment risks
| # | Risk | L | I | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| P1 | **Entire feature layer is uncommitted** — no clean/tagged baseline for Phase-1 | High | High | Commit + tag before Phase-1 |
| P2 | Python version mismatch (CI 3.11 vs Render 3.12) | Low | Med | Reconcile |
| P3 | Multiple features activated simultaneously without independent shadow | Low | High | Phased roadmap: one shadow->active at a time |
| P4 | Alembic head-gate may reject startup if uncommitted migrations aren't applied to target env | Med | High | Ensure all 24 migrations (incl. uncommitted realism/sector/regime cols) applied to Render |

---

## 9. Implementation Blockers

| # | Blocker | Severity | Reason | Resolution | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| B1 | Feature layer uncommitted (services, migrations, specs, ADRs, tests, modified core files) | **Critical** | No clean/tagged baseline; Phase-1 cannot start from a dirty tree; rollback guarantees unverifiable | Commit + tag a Phase-0 baseline | System Owner |
| B2 | ADR-003 mandates FEAT-007 spec revision (ratio->difference) but constraint forbids modifying FEAT docs | **Critical** | FEAT-007 cannot be scoped/implemented without resolving which artifact is authoritative | System Owner decision: revise FEAT-007 spec OR issue a superseding governance note | System Owner |
| B3 | ADR-001/002 acceptance status mismatch (files say "Proposed"; README stale) | **High** | Phase-1/2 gating decisions unverified | Update ADR file headers + README to reflect accepted status, or formal sign-off | System Owner |
| B4 | ADR-001 default (`REALISTIC`) vs FEAT-008 spec example default (`LEGACY`) conflict | **High** | Determines whether Phase-1 is "add switch" or "add switch + flip composite" | System Owner adjudication; ADR-001 strongly recommends REALISTIC default | System Owner |
| B5 | No `feat004/007/008` config sections in `settings.py` | **High** | No flag-based rollback possible | Add three pydantic config blocks | Implementer |
| B6 | FEAT-004 not wired (agent never passes overlay inputs) | **High** | Feature is dead code; no production effect | Wire `RecommendationAgent.run()` + benchmark fetch + sector cache | Implementer |
| B7 | FYERS index/sector instrument support unverified | **High** | Blocks FEAT-004/007 benchmark + sector fetch | Verify `NIFTY500`/`NIFTY50`/`NSE:NIFTY*-INDEX`; confirm yfinance fallback | Implementer |
| B8 | `sector_mappings.json` coverage unverified (80 symbols vs ~500+ universe) | **High** | Silent UNKNOWN abstentions for unmapped symbols | Expand + peer-review mapping | System Owner + reviewer |
| B9 | Cost schedule figures unverified vs contract note | **Medium** | Wrong figures worse than configurable placeholders | Verify slippage/brokerage/STT/exchange/GST/stamp/SEBI bps | System Owner |
| B10 | Conservative exit ordering + `skip_on_missing_next_bar` + end-of-data edge case absent | **Medium** | FEAT-008 Section 9.3/9.4 not fully satisfied | Implement + test | Implementer |
| B11 | `test_feat008*` / `test_feat007*` missing | **Medium** | Regression gates absent | Author per spec test plans | Implementer |
| B12 | Frontend forward-compat + log capacity unverified | **Medium** | Shadow writes full payload | Verify | Implementer |

---

## 10. Phase-0 Checklist

| # | Item | Status | Priority | Owner | Est. effort |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Commit + tag the feature-layer working tree as Phase-0 baseline | Not done | P0/Critical | System Owner | 0.5d |
| 2 | Reconcile ADR-001/002/003 acceptance status in files + README | Needs Verification | P0/High | System Owner | 0.5d |
| 3 | Resolve ADR-003 vs FEAT-007 spec-revision conflict | Open | P0/Critical | System Owner | 0.5d (decision) |
| 4 | Adjudicate ADR-001 default vs FEAT-008 spec default (REALISTIC vs LEGACY) | Open | P0/High | System Owner | 0.5d (decision) |
| 5 | Add `feat008` config section to `settings.py` | Missing | P0/High | Implementer | 0.5d |
| 6 | Add `feat004` config section to `settings.py` | Missing | P0/High | Implementer | 0.5d |
| 7 | Add `feat007` config section to `settings.py` (inert placeholder) | Missing | P1/Medium | Implementer | 0.25d |
| 8 | Verify FYERS index/sector instrument support (+ yfinance fallback) | Needs Verification | P0/High | Implementer | 1d |
| 9 | Peer-review + extend `sector_mappings.json` to full universe | Partial | P0/High | System Owner + reviewer | 1d |
| 10 | Verify broker/NSE cost schedule vs contract note | Needs Verification | P0/Medium | System Owner | 0.5d |
| 11 | Wire FEAT-004 into live pipeline (agent -> service inputs + benchmark fetch) | Not done | P0/High | Implementer | 1.5d |
| 12 | Verify frontend forward-compat with nested recommendation keys | Needs Verification | P0/Medium | Implementer | 0.5d |
| 13 | Verify log storage/rotation for ~3x payload growth | Needs Verification | P0/Medium | Implementer | 0.5d |
| 14 | Implement conservative exit ordering + `skip_on_missing_next_bar` + end-of-data fix | Missing | P0/Medium | Implementer | 1d |
| 15 | Author `test_feat008*` (15 tests, esp. byte-identity/causality/conservative) | Missing | P0/Medium | Implementer | 1d |
| 16 | Author `test_feat007*` (14 tests + cross-feature abstention) | Missing | P1/Medium | Implementer | 0.75d |
| 17 | ADR-002: rename SR-004 states + document FEAT-004/SR-004 boundary | Not done | P1/Medium | Implementer | 0.5d |
| 18 | Reconcile Python version (CI 3.11 vs Render 3.12) | Needs Verification | P2/Low | Implementer | 0.25d |
| 19 | Hygiene: dedupe `db/session.py`, consolidate route folders | Not done | P2/Low | Implementer | 0.5d |

---

## 11. Go / No-Go Decision

### **NO-GO.** Implementation cannot begin until the following are completed.

**Critical blockers (must close first):**
1. **Commit + tag the Phase-0 baseline.** The entire feature layer is uncommitted. Phase-1 must start from a clean, reproducible, rollback-able baseline.
2. **Resolve the ADR-003 vs FEAT-007 spec conflict.** Accepted ADR-003 requires the FEAT-007 specification to be revised to the difference formula, which contradicts the "do not modify FEAT documents" constraint. The System Owner must decide which artifact is authoritative before FEAT-007 can be scoped.
3. **Reconcile ADR-001/ADR-002 acceptance status** in the file headers and `docs/adr/README.md` with the stated governance, and **adjudicate the ADR-001 default vs FEAT-008 spec default** (REALISTIC vs LEGACY).

**High blockers (must close before the respective phase):**
4. Add `feat004`/`feat007`/`feat008` config sections to `settings.py` (no flag-based rollback exists today).
5. Wire FEAT-004 into the live pipeline (currently dead code).
6. Verify FYERS index/sector instrument support and `sector_mappings.json` universe coverage.
7. Verify broker/NSE cost schedule, frontend forward-compatibility, and log capacity.

**Once items 1-3 are closed**, Phase-1 (FEAT-008 substrate finalization per ADR-001 Option B) may begin. **Once items 4-7 are closed**, Phase-2 (FEAT-004 activation per ADR-002 Option C) may begin. **Once the ADR-003 spec revision is executed and FEAT-004 sector plumbing is live**, Phase-3 (FEAT-007 per ADR-003 Option C-Revised) may begin.

---

*End of PHASE0_REPOSITORY_READINESS_REPORT v1.0*
