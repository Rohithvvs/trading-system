# FEAT008_IMPLEMENTATION_ANALYSIS.md

**Feature:** FEAT-008 — Realistic Trade Execution Model
**Phase:** 1 — Implementation Preparation
**Role:** Staff Software Engineer / Brownfield Repository Architect
**Date:** 2026-07-12
**Method:** Repository evidence only. No code generated. No architecture redesigned.
**Status:** Analysis complete — ready for implementation planning.

---

## Methodology & Evidence Base

This report is derived from a line-by-line audit of the current codebase (2026-07-12). Every claim is grounded in a cited file and line number. Where the codebase does not provide evidence, the item is marked **Needs Verification**.

Cross-referenced governance artifacts (already in the repository):
- `FEAT-008_REALISTIC_TRADE_EXECUTION_MODEL.md` — the specification (v1.0)
- `docs/adr/ADR-001_backtest_execution_model.md` — the architectural decision record (Proposed, not final)
- `IMPLEMENTATION_MASTER_PLAN.md` — the approved execution guide (Phase 1 = FEAT-008)
- `IMPLEMENTATION_PLANNING_REVIEW.md` — the approved implementation order (FEAT-008 → FEAT-004 → FEAT-007)

---

## 1. Where Backtest Execution Begins

Backtest execution has **one production entry point** and **one validation-only entry point**.

### 1.1 Production entry point (feeds recommendations)

| Layer | Location | Trigger |
| :--- | :--- | :--- |
| Orchestration | `orchestrator_agent.py:529` — `self.backtest_agent.run(symbol, mode, candles_by_mode[mode])` | Called inside `_analyze_symbol_post_bulk()`, dispatched via `asyncio.to_thread(run_backtest)` (`orchestrator_agent.py:547-548`) |
| Agent | `backtest_agent.py:11` — `BacktestAgent.run()` | Thin pass-through to service |
| Service | `backtest_service.py:171` — `BacktestService.run()` | The actual engine; runs two passes every call |

The backtest agent is instantiated once per `OrchestratorAgent` construction (`orchestrator_agent.py:47`). It is invoked once per `(symbol, mode)` pair — i.e., twice per symbol when `mode = both` (intraday + swing).

### 1.2 Validation-only entry point (does NOT feed recommendations)

| Layer | Location | Purpose |
| :--- | :--- | :--- |
| Service | `walk_forward_service.py:135` — `WalkForwardService._simulate_backtest()` | A **separate** backtest loop used for walk-forward validation. Adds regime gating (VIX/breadth/trend veto). **Imports** `calculate_transaction_costs`, `COST_SCENARIOS`, `PercentEquityPositionSizer` from `backtest_service.py:13`. |

This second path is critical context: it shares the realism utilities but is structurally independent. It does **not** call `BacktestService.run()`. Its output does not feed the composite. **Needs Verification** whether the FEAT-008 switch should propagate to this path.

---

## 2. Complete Execution Flow (Call Chain)

### 2.1 Full production call chain (recommendation path)

```
OrchestratorAgent.run_full(request)                      [orchestrator_agent.py:52]
  │
  ├─ Prefetch OHLCV for all symbols concurrently          [orchestrator_agent.py:67-95]
  │    └─ self.fyers_service.fetch_ohlcv(...)             [orchestrator_agent.py:73-78]
  │
  ├─ Bulk technical analysis (vectorized)                [orchestrator_agent.py:108-110]
  │    └─ self.technical_agent.run_bulk(...)              [orchestrator_agent.py:110]
  │
  └─ _analyze_symbol_post_bulk(symbol, ...)               [orchestrator_agent.py:480]
       │
       ├─ _run_agents_concurrently()                       [orchestrator_agent.py:524]
       │    └─ run_backtest()  [in thread]                 [orchestrator_agent.py:525]
       │         └─ for mode in modes:
       │              self.backtest_agent.run(symbol, mode, candles)   [orchestrator_agent.py:529]
       │                └─ BacktestAgent.run()              [backtest_agent.py:11]
       │                     └─ self.service.run(symbol, mode, candles, cost_scenario, position_sizing_pct)
       │                                                  [backtest_agent.py:18]
       │                        └─ BacktestService.run()  [backtest_service.py:171]
       │                             ├─ Pass 1: gross/legacy loop     [backtest_service.py:221-278]
       │                             ├─ Pass 2: realistic/net loop   [backtest_service.py:326-456]
       │                             ├─ End-of-data force-close       [backtest_service.py:458-498]
       │                             ├─ Net metric computation       [backtest_service.py:500-529]
       │                             └─ returns BacktestResult       [backtest_service.py:537-565]
       │
       ├─ best_backtest = max(backtests, key=item.total_return)   [orchestrator_agent.py:566]
       │
       ├─ recommendation_agent.run(..., backtests=backtests, ...)  [orchestrator_agent.py:567]
       │    └─ RecommendationService.build()              [recommendation_service.py:23]
       │         ├─ best_backtest = max(backtests, key=item.total_return)  [recommendation_service.py:39]
       │         ├─ raw_backtest = min(max(best_backtest.total_return * 4, -20), 100)  [recommendation_service.py:64]
       │         ├─ composite = raw_tech*tech_wt + raw_backtest*backtest_wt + ...        [recommendation_service.py:68]
       │         ├─ label = BUY if score>=72, WATCH if score>=55, else REJECT           [recommendation_service.py:86-91]
       │         └─ apply_feat004_regime_overlay(...)     [recommendation_service.py:100]
       │
       ├─ _enforce_strict_buy_gate(recommendation, backtests, ...) [orchestrator_agent.py:578]
       │
       ├─ sector_overlay = sector_rs_service.evaluate_sector_overlay(...)  [orchestrator_agent.py:594]
       ├─ market_regime = market_permission_service.evaluate_market_permission(...) [orchestrator_agent.py:603]
       │
       └─ _persist_analysis(stock_id, ..., backtest=best_backtest, ...)  [orchestrator_agent.py:646]
            ├─ AnalysisHistory(backtest_score=backtest.total_return)     [orchestrator_agent.py:705]
            └─ BacktestHistory(total_return=backtest.total_return,
                 gross_total_return=getattr(backtest,"gross_total_return",None), ...) [orchestrator_agent.py:727-748]
```

### 2.2 Validation-only call chain (walk-forward, does NOT feed recommendations)

```
WalkForwardService._simulate_backtest(symbol, candles_df, regime_df, ...)  [walk_forward_service.py:135]
  ├─ imports calculate_transaction_costs, COST_SCENARIOS, PercentEquityPositionSizer
  │   from backtest_service                                         [walk_forward_service.py:13]
  ├─ Uses COST_SCENARIOS["BASE_COST"] hardcoded                     [walk_forward_service.py:165]
  ├─ Same pending_buy/pending_exit state machine (causal next-bar open)
  ├─ Adds regime gating: veto entries on HIGHRISK/DEFENSIVE; risk_multiplier on CAUTIOUS
  └─ Returns (metrics_dict, vetoes_list) — does NOT return BacktestResult
```

---

## 3. Files Involved

### 3.1 Direct backtest files (the FEAT-008 surface)

| File | Role | Lines (key) |
| :--- | :--- | :--- |
| `backend/app/services/backtest_service.py` | The engine — Pass 1 (gross), Pass 2 (realistic), cost model, sizing, CAGR | 601 total |
| `backend/app/agents/backtest_agent.py` | Thin agent wrapper delegating to service | 19 total |
| `backend/app/schemas/analysis.py` | `BacktestResult` Pydantic model (the data contract) | lines 92-120 |
| `backend/app/models/analysis.py` | `BacktestHistory` SQLAlchemy ORM (persistence) | lines 45-72 |
| `backend/alembic/versions/add_backtest_realism_metrics.py` | DB migration adding 10 realism columns (already applied) | 61 total |

### 3.2 Consumer files (read backtest output, must remain consistent)

| File | Role | Key lines |
| :--- | :--- | :--- |
| `backend/app/agents/orchestrator_agent.py` | Calls backtest, selects `best_backtest` by `total_return`, feeds composite, persists | 529, 566, 705, 727-748 |
| `backend/app/agents/recommendation_agent.py` | Passes `backtests` list to `RecommendationService.build()` | 42-49 |
| `backend/app/services/recommendation_service.py` | Composite score formula; reads `best_backtest.total_return` | 39, 64, 68, 193-196 |
| `backend/app/services/walk_forward_service.py` | Separate validation backtest; imports realism utilities from backtest_service | 13, 135-624 |

### 3.3 Config & logging infrastructure

| File | Role |
| :--- | :--- |
| `backend/app/config/settings.py` | Pydantic `BaseSettings`, `.env`-backed — **no feat008 section exists** |
| `backend/app/utils/logger.py` | `get_logger()` + `RotatingFileHandler` (10 MB, 5 backups) |

---

## 4. Classes Involved

| Class | File | Responsibility |
| :--- | :--- | :--- |
| `BacktestAgent` | `backtest_agent.py:7` | Agent facade; delegates to `BacktestService` |
| `BacktestService` | `backtest_service.py:170` | The engine; runs Pass 1 + Pass 2 |
| `PositionSizer` (ABC) | `backtest_service.py:148` | Abstract sizing interface |
| `PercentEquityPositionSizer` | `backtest_service.py:156` | Fractional-equity sizing |
| `BacktestResult` | `schemas/analysis.py:92` | Pydantic data contract for backtest output |
| `BacktestHistory` | `models/analysis.py:45` | ORM model for DB persistence |
| `OrchestratorAgent` | `orchestrator_agent.py:39` | Calls backtest; selects best; feeds composite; persists |
| `RecommendationAgent` | `recommendation_agent.py:8` | Passes backtests into composite builder |
| `RecommendationService` | `recommendation_service.py:22` | Composite score; dynamic weights; backtest→points |
| `WalkForwardService` | `walk_forward_service.py:21` | Separate validation backtest with regime gating |
| `Settings` | `config/settings.py:57` | Pydantic BaseSettings (env-backed config) |

---

## 5. Functions Involved

### 5.1 Backtest engine functions

| Function | Location | Purpose |
| :--- | :--- | :--- |
| `BacktestService.run()` | `backtest_service.py:171` | Main entry; runs Pass 1 + Pass 2; returns `BacktestResult` |
| `BacktestService._empty_result()` | `backtest_service.py:567` | Fallback for <35 candles |
| `calculate_transaction_costs(side, price, qty, mode, config)` | `backtest_service.py:58` | Indian cost stack — brokerage, STT, exchange, SEBI, stamp, GST, DP |
| `calculate_cagr(initial, ending, days)` | `backtest_service.py:129` | Geometric annualized return |
| `PercentEquityPositionSizer.calculate_shares()` | `backtest_service.py:160` | `int((equity * pct/100) // price)` |

### 5.2 Consumer functions (backtest-score consumers)

| Function | Location | How it uses backtest |
| :--- | :--- | :--- |
| `OrchestratorAgent._analyze_symbol_post_bulk()` | `orchestrator_agent.py:480` | Calls `backtest_agent.run()`; selects `best_backtest` by `total_return` |
| `OrchestratorAgent._persist_analysis()` | `orchestrator_agent.py:687` | Writes `backtest_score=backtest.total_return` to `AnalysisHistory`; writes full `BacktestHistory` row |
| `OrchestratorAgent._enforce_strict_buy_gate()` | `orchestrator_agent.py:901` | Reads `best_backtest.verdict` and `best_backtest.total_return` for gate diagnostics |
| `OrchestratorAgent._confidence_breakdown()` | `orchestrator_agent.py:1011` | Reads `backtest.total_return`, `backtest.verdict`, `backtest.trade_count` |
| `RecommendationService.build()` | `recommendation_service.py:23` | `raw_backtest = min(max(best_backtest.total_return * 4, -20), 100)` |
| `RecommendationService.calculate_dynamic_weights()` | `recommendation_service.py:167` | Selects backtest weight 0.25 (standard) / 0.20 (catalyst) |
| `RecommendationService._backtest_component()` | `recommendation_service.py:193` | `min(max(backtest.total_return * 2, -5), 25)` — unused by composite path (raw_backtest is used instead) |
| `RecommendationService._build_trade_plans()` | `recommendation_service.py:198` | Reads `backtest.verdict`, `backtest.strategy_name` for trade-plan notes |

### 5.3 Validation-only functions

| Function | Location | Purpose |
| :--- | :--- | :--- |
| `WalkForwardService._simulate_backtest()` | `walk_forward_service.py:135` | Separate backtest loop with regime gating; returns `(dict, list)` — not `BacktestResult` |

---

## 6. Current Execution Model

The engine runs **two passes every time**, hardwired, with no caller-selectable switch. Both passes run on the same `candles` input and the same indicator computation, but with different fill timing, cost, and sizing models.

### 6.1 Pass 1 — Gross / Legacy baseline

| Aspect | Behavior | Evidence |
| :--- | :--- | :--- |
| **Entry timing** | Signal on `close[T]` → fill at `close[T]` (same candle). **Non-causal.** | `backtest_service.py:240` — `gross_position_entry = float(row["close"])` |
| **Exit timing** | Signal on `close[T]` → fill at `close[T]` (same candle). **Non-causal.** | `backtest_service.py:244` — `exit_price = float(row["close"])` |
| **Fill price** | Raw `row["close"]` — no adjustment | `backtest_service.py:240, 244, 267` |
| **Cost calculation** | None | No cost function called in Pass 1 loop |
| **Slippage** | None | No slippage in Pass 1 |
| **Brokerage** | None | No brokerage in Pass 1 |
| **Taxes / Statutory** | None | None in Pass 1 |
| **Position sizing** | Implicit 100% — `gross_equity *= 1 + (trade_return / 100)` | `backtest_service.py:253, 276` |
| **Reported as** | `gross_total_return`, `gross_cagr`, `gross_max_drawdown`, `gross_win_rate`, `gross_profit_factor`, `gross_sharpe_ratio` | `backtest_service.py:281-299, 554-559` |

### 6.2 Pass 2 — Realistic / Net challenger

| Aspect | Behavior | Evidence |
| :--- | :--- | :--- |
| **Entry timing** | Signal on `close[T]` → `pending_buy=True` → fill at `open[T+1]`. **Causal.** | `backtest_service.py:336-341` — `entry_price = float(row["open"])` executed at start of next iteration |
| **Exit timing** | Signal on `close[T]` → `pending_exit=True` → fill at `open[T+1]`. **Causal.** | `backtest_service.py:369-370` — `exit_price = float(row["open"])` |
| **Fill price** | `open[T+1]` adjusted by slippage (multiplicative) | `backtest_service.py:341, 374` |
| **Slippage** | Symmetric multiplier: buy `×(1 + slippage_rate)`, sell `×(1 − slippage_rate)`. Three tiers via `COST_SCENARIOS`: 0.02% / 0.05% / 0.15% | `backtest_service.py:341, 374`; `COST_SCENARIOS` at `19-56` |
| **Brokerage** | `%` of turnover with optional flat cap (₹20). Via `calculate_transaction_costs` | `backtest_service.py:83-85` |
| **Taxes / Statutory** | **Full Indian stack** (richer than spec): STT (intraday 0.025% sell-only / delivery 0.1% both), exchange transaction charges, SEBI, stamp duty (buy-only: 0.015% delivery / 0.003% intraday), GST 18% on (brokerage+exchange+SEBI), DP charge ₹13.5 sell-side delivery | `backtest_service.py:58-127` |
| **Cost config** | `COST_SCENARIOS = {"LOW_COST", "BASE_COST", "STRESS_COST"}` — module-level dict, selected by `cost_scenario` param | `backtest_service.py:19-56, 318` |
| **Position sizing** | `PercentEquityPositionSizer` (fractional, default 20%) — quantity adjusted to fit cash including fees | `backtest_service.py:319, 342, 350-353` |
| **Same-session retro-fee** | If intraday mode and `entry_date == exit_date`, retroactively adjusts entry fee from delivery to intraday rates and refunds the difference | `backtest_service.py:377-392` |
| **End-of-data edge case** | Open position at end of data force-closed at `final_row["close"]` (close[T]) — **residual non-causal**. Logged as `TEMPORARY_ASSUMPTION` warning | `backtest_service.py:458-498` |
| **Intrabar stop/target** | **Not implemented.** Exit is signal-based only (EMA/MACD/RSI). No stop-loss or target-price levels are tracked or evaluated intrabar. | `backtest_service.py:443-456` — only `exit_signal` check |
| **Reported as** | `total_return`, `cagr`, `max_drawdown`, `win_rate`, `profit_factor`, `trade_count`, `verdict`, `sharpe_ratio`, `equity_curve`, `trades`, `monthly_returns`, `best_trade`, `worst_trade` | `backtest_service.py:500-565` |

### 6.3 Which pass feeds the composite — THE load-bearing fact (D1)

This is the single most important finding for FEAT-008, and it is now **answered by repository evidence**:

| Consumer | Code | Uses which metric |
| :--- | :--- | :--- |
| `OrchestratorAgent` best-backtest selection | `orchestrator_agent.py:566` — `max(backtests, key=lambda item: item.total_return)` | **Pass 2** (`total_return` = net realistic return, `backtest_service.py:501, 541`) |
| `RecommendationService` composite input | `recommendation_service.py:64` — `raw_backtest = min(max((best_backtest.total_return * 4) ...))` | **Pass 2** (`total_return`) |
| `AnalysisHistory` persistence | `orchestrator_agent.py:705` — `backtest_score=backtest.total_return` | **Pass 2** (`total_return`) |
| `BacktestHistory` persistence | `orchestrator_agent.py:731` — `total_return=backtest.total_return` | **Pass 2** |
| Pass 1 metrics persistence | `orchestrator_agent.py:738-747` — `gross_total_return`, `gross_cagr`, etc. | Persisted but **does NOT feed composite** |

**Conclusion (D1 RESOLVED):** The composite's backtest weight (25% standard / 20% catalyst) is already fed by **Pass 2 — the realistic, cost-aware, causal net metric**. Pass 1 (gross/legacy) is computed and persisted for comparison only. The FEAT-008 "substrate shift" described in the spec has **already happened in production**.

This matches ADR-001 §2's finding ("the FEAT-008 substrate shift has already happened") and ADR-001 §7's recommendation (Option B: default `execution_model = REALISTIC` to preserve today's behavior; defaulting to `LEGACY` would be a silent behavior change).

### 6.4 What does NOT exist (gaps FEAT-008 must add)

Confirmed by grep across `backend/`:
- No `execution_model` parameter, enum, or runtime switch.
- No `composite_uses_realistic` flag.
- No `feat008` identifier anywhere.
- No `LEGACY`/`REALISTIC` tokens as identifiers (only as log message labels: `"REALISTIC ENTRY"`, `"REALISTIC EXIT"` at `backtest_service.py:364, 415`).
- No way for a caller to select Pass 1 only, Pass 2 only, or both.
- No conservative intrabar stop-before-target ordering (spec §9.3). The exit logic is purely signal-based.

---

## 7. Which Files FEAT-008 Will Modify

Per `IMPLEMENTATION_MASTER_PLAN.md` §6 (Phase 1) and ADR-001 §8 (Option B migration):

| # | File | Change | Evidence basis |
| :--- | :--- | :--- | :--- |
| 1 | `backend/app/services/backtest_service.py` | Add `execution_model: Literal["LEGACY","REALISTIC"]` param to `run()` (default `REALISTIC` per ADR-001 §7); route LEGACY→Pass 1 as primary / REALISTIC→Pass 2 as primary with Pass 1 as `legacy_*` shadow; brand as feat008; verify/add conservative intrabar stop/target ordering (spec §9.3 — currently absent) | `backtest_service.py:171` signature; §6.4 gaps |
| 2 | `backend/app/agents/backtest_agent.py` | Pass-through `execution_model` param to `BacktestService.run()` | `backtest_agent.py:11-18` current signature |
| 3 | `backend/app/config/settings.py` | Add `feat008` config section: `enabled`, `execution_model`, `composite_uses_realistic`, `cost_scenario`, `conservative_exit_ordering`, `skip_on_missing_next_bar` (spec §13) | `settings.py:57` — no feat008 section exists |
| 4 | `backend/app/schemas/analysis.py` | Expose `feat008_*` fields on `BacktestResult` (spec §12.2): `feat008_enabled`, `feat008_execution_model`, `feat008_*_bps`, `feat008_trades_skipped`, `feat008_score_used`, `feat008_explanation`, etc. | `schemas/analysis.py:92-120` — current `BacktestResult` |
| 5 | `backend/app/agents/orchestrator_agent.py` | Implement `composite_uses_realistic` gate at the point where `backtest_score` is selected (line 566/705). In shadow (`composite_uses_realistic=false`), composite uses legacy `gross_total_return`; in active (`true`), uses `total_return`. Pass feat008 config to backtest calls. | `orchestrator_agent.py:529, 566, 705` |
| 6 | `backend/app/tests/test_backtest_realism.py` | Extend with FEAT-008 §16.2 test cases not already covered (conservative stop-before-target ordering, LEGACY purity/byte-identity, causality guard, skip-on-missing-next-bar, no-propagation-on-exception). Existing 11 tests must remain green. | `test_backtest_realism.py` — current 11 tests |
| 7 | `backend/app/models/analysis.py` | **Conditional.** If `feat008_execution_model` / `feat008_score_used` must persist, add 2 nullable columns to `BacktestHistory` + a small idempotent Alembic migration. Master plan §12 says "likely none" — the 10 realism columns already exist. | `models/analysis.py:45-72`; `alembic/versions/add_backtest_realism_metrics.py` |

**Decision required before coding (D1, per master plan §4.4):** The default value of `execution_model`.
- ADR-001 §7 recommends **default `REALISTIC`** because the composite already uses Pass 2 — defaulting to `LEGACY` would flip the composite to Pass 1 (a silent global behavior change, opposite of brownfield safety).
- The spec §13 suggests default `LEGACY`. **Needs Verification** — System Owner must confirm ADR-001 Option B before implementation.

---

## 8. Which Files FEAT-008 Must NOT Modify

Per FEAT-008 spec §17 (Brownfield Safety Confirmation) and ADR-001 §2:

| File / Component | Reason | Evidence |
| :--- | :--- | :--- |
| `backend/app/services/feat004_regime_overlay.py` | FEAT-004 territory (Phase 2). FEAT-008 is `COMP-BT`; FEAT-004 is `COMP-REC`. | spec §4 |
| `backend/app/services/sector_rs_service.py` (SR-003) | FEAT-007 territory (Phase 3). | spec §4 |
| `backend/app/services/market_permission_service.py` (SR-004) | Live market-regime gate; FEAT-004 reconciliation (Phase 2). | ADR-001 §2 |
| Strict Buy Gate logic in `orchestrator_agent.py:_enforce_strict_buy_gate()` | Gate thresholds and criteria are unchanged. FEAT-008 changes the *input* to the composite, not the gate. | spec §17; `orchestrator_agent.py:901-996` |
| BUY/WATCH/REJECT thresholds (72 / 55) in `recommendation_service.py` | Thresholds unchanged; only the backtest *score input* changes. | spec §17; `recommendation_service.py:86-91` |
| Composite normalization formula in `recommendation_service.py:build()` | `COMP-REC` normalization untouched. FEAT-008 changes raw trade outcomes, not the formula. | spec §4, §17 |
| Technical analysis indicator logic (`technical_analysis_service.py`, `technical_analysis_agent.py`) | `COMP-TA` — no indicator or price-action changes. | spec §4 |
| Data fetching / FYERS / caching (`fyers_service.py`, `market_data_service.py`) | `COMP-MD` — no data-provider changes. FEAT-008 adds no new data. | spec §4, §11 |
| `backend/app/services/walk_forward_service.py` | **Needs Verification.** Separate validation path that imports realism utilities. If `calculate_transaction_costs` / `COST_SCENARIOS` signatures are unchanged, this file need not be modified. If the switch must propagate to walk-forward validation, it becomes a Phase-1-adjacent task — but it does not feed recommendations. | `walk_forward_service.py:13, 135` |

---

## 9. Existing Reusable Utilities

FEAT-008 must **reuse, not rewrite**, the following (per master plan §4.2 "preserve, do not rewrite"):

| Utility | Location | Status | Reuse in FEAT-008 |
| :--- | :--- | :--- | :--- |
| `calculate_transaction_costs(side, price, qty, mode, config)` | `backtest_service.py:58-127` | Live, tested (11 tests) | **Reuse as-is.** Richer than spec's `apply_costs` — models 7 components with intraday/delivery branching. Spec §10.2's `apply_costs` is a simplification; the existing function is a superset. |
| `COST_SCENARIOS` (`LOW_COST`, `BASE_COST`, `STRESS_COST`) | `backtest_service.py:19-56` | Live | **Reuse as-is.** Map `feat008.cost_scenario` config key to select among these. Spec's `slippage_bps`/`brokerage_bps`/`statutory_bps` are aggregate config keys — the existing dict models each component individually. **Needs Verification** on mapping approach (aggregate-bps vs per-component). |
| `PercentEquityPositionSizer` / `PositionSizer` ABC | `backtest_service.py:148-164` | Live, tested | **Reuse as-is.** |
| `calculate_cagr()` | `backtest_service.py:129-143` | Live, tested | **Reuse as-is.** |
| Pending-order state machine (`pending_buy`/`pending_exit`) | `backtest_service.py:322-456` | Live, tested | **Reuse as-is.** This IS the causal next-bar-open execution model. |
| Retro-intraday fee adjustment | `backtest_service.py:377-392` | Live, tested | **Preserve** — complex same-session detection; modifying the exit path must not break this. |
| `get_logger()` + `RotatingFileHandler` | `utils/logger.py` | Live | **Reuse as-is** for feat008 log fields. |
| `BacktestResult` schema (with realism fields) | `schemas/analysis.py:92-120` | Live | **Extend** with `feat008_*` fields; do not remove existing `gross_*` / `total_transaction_costs` / `total_slippage` fields. |

---

## 10. Configuration Points

### 10.1 Current configuration mechanism

| Mechanism | Location | Details |
| :--- | :--- | :--- |
| Pydantic `BaseSettings` | `config/settings.py:57` | `.env`-backed; `model_config = SettingsConfigDict(env_file=ROOT_DIR/.env)` (`settings.py:109-114`) |
| `cost_scenario` param | `BacktestService.run()` signature (`backtest_service.py:176`) | Hardcoded default `"BASE_COST"`; **not** config-driven at the call site. Passed through from `BacktestAgent.run()` default. |
| `position_sizing_pct` param | `BacktestService.run()` signature (`backtest_service.py:177`) | Hardcoded default `20.0`; **not** config-driven. |
| `COST_SCENARIOS` dict | `backtest_service.py:19-56` | Module-level constant — not env-overridable. |
| Orchestrator call | `orchestrator_agent.py:529` | `self.backtest_agent.run(symbol, mode, candles_by_mode[mode])` — passes **no** `cost_scenario` or `position_sizing_pct`, so engine defaults apply. |

### 10.2 What FEAT-008 must add (per spec §13)

```yaml
feat008:
  enabled: true
  execution_model: "REALISTIC"     # per ADR-001 §7 (preserves today's behavior)
  composite_uses_realistic: true   # per ADR-001 §7 (composite already uses total_return)
  cost_scenario: "BASE_COST"
  conservative_exit_ordering: true
  skip_on_missing_next_bar: true
```

**No new config framework.** Add a `feat008` section to `Settings` in `settings.py` (nested Pydantic model or flat prefixed fields, consistent with existing pattern).

**Gap:** The spec §13 specifies `slippage_bps`, `brokerage_bps`, `statutory_bps` as separate aggregate keys. The existing `COST_SCENARIOS` models 7+ individual components with rates and flat caps. **Needs Verification** — System Owner must decide: (a) add aggregate-bps config that overrides `COST_SCENARIOS`, or (b) expose `COST_SCENARIOS` values via config and keep the granular model. ADR-001 §4 notes the existing model is "richer than the spec."

---

## 11. Logging Points

### 11.1 Existing backtest logging

| Logger | Location | Log messages |
| :--- | :--- | :--- |
| `logger = get_logger("app.backtest")` | `backtest_service.py:14` | — |
| Realistic entry | `backtest_service.py:363-366` | `"REALISTIC ENTRY \| symbol=%s \| qty=%d \| raw_price=%.2f \| exec_price=%.2f \| cost=%.2f \| date=%s"` (INFO) |
| Realistic exit | `backtest_service.py:414-417` | `"REALISTIC EXIT \| symbol=%s \| qty=%d \| raw_price=%.2f \| exec_price=%.2f \| cost=%.2f \| pnl=%.2f%% \| date=%s"` (INFO) |
| Retroactive cost adjustment | `backtest_service.py:392` | `"RETROACTIVE COST ADJUSTMENT \| Same-session trade. Refunded delivery fee difference: %.2f"` (INFO) |
| End-of-data force-close | `backtest_service.py:487-490` | `"TEMPORARY_ASSUMPTION \| Position still open at end of backtest. Forcing exit at final candle close \| ..."` (WARNING) |
| Orchestrator backtest failure | `orchestrator_agent.py:531` | `"Backtest agent failed for %s in %s mode: %s"` (ERROR) — catches and returns error-fallback `BacktestResult` |
| Strict Buy Gate diagnostic | `orchestrator_agent.py:922-934` | `"STRICT BUY GATE EVALUATE \| ... backtest_verdict=%s \| backtest_return=%.2f ..."` (INFO) |
| Confidence breakdown | `orchestrator_agent.py:1011-1026` | `backtest_return`, `backtest_component` in the breakdown dict |

### 11.2 Logging infrastructure

| Component | Location | Details |
| :--- | :--- | :--- |
| `get_logger()` | `utils/logger.py:52` | Returns `logging.getLogger(name)` |
| `configure_logging()` | `utils/logger.py:21` | Root logger at INFO; `RotatingFileHandler` 10 MB, 5 backups |
| Log directory | `utils/logger.py:14` | `backend/logs/` (or `TEST_ARTIFACT_DIR/logs` in tests) |
| Per-test log files | `backend/tests/conftest.py:122-147` | Each test gets its own log file in `tests/artifacts/backend/logs/` |
| pytest log file | `pytest.ini:4` (root) | `--log-file=tests/artifacts/backend/pytest.log --log-file-level=INFO` |

### 11.3 What FEAT-008 must add (per spec §14)

Per spec §14, every field must be written on every stock, regardless of mode; absent values explicitly `null`. The `feat008_*` fields (spec §12.2) should be added to the `BacktestResult` payload so they propagate through the orchestrator's persistence and confidence-breakdown paths.

**Key fields to add:** `feat008_enabled`, `feat008_execution_model`, `feat008_total_cost_bps_per_side`, `feat008_trades_simulated`, `feat008_trades_skipped`, `feat008_win_rate`, `feat008_profit_factor`, `feat008_legacy_win_rate`, `feat008_legacy_profit_factor`, `feat008_score_used`, `feat008_explanation`.

---

## 12. Unit Tests Already Available

### 12.1 Backtest realism suite — `backend/app/tests/test_backtest_realism.py`

**11 tests** in `TestBacktestRealism` (unittest.TestCase). All deterministic, all offline (mock candles).

| # | Test | What it validates | FEAT-008 §16.2 coverage |
| :--- | :--- | :--- | :--- |
| 1 | `test_next_day_open_execution_and_gross_net_comparison` | Entry at open[T+1]=112, slippage applied; gross (close-based) vs net (open-based) differ; net return < 0; costs > 0; slippage > 0 | Covers §16.2 #2 (entry next-bar open), #10 (costs reduce PnL) |
| 2 | `test_position_sizing_allocation` | 20% sizing produces trades; `position_sizing_pct` reflected in result | Related to sizing (not in §16.2 list) |
| 3 | `test_cost_scenarios_comparison` | STRESS_COST > LOW_COST in both `total_transaction_costs` and `total_slippage` | Related to costs (not in §16.2 list) |
| 4 | `test_transaction_cost_details` | Direct `calculate_transaction_costs` math for swing (₹17.82 on ₹10k turnover) and intraday (cheaper) | Covers §16.2 #15 (cost components sum) — partially |
| 5 | `test_no_fake_entry_day_drawdown_from_state_leakage` | Equity curve on signal day and entry day stays ~100k (no state leak) | Regression guard, not in §16.2 |
| 6 | `test_cagr_calculation_uses_unique_trading_days` | 100 candles same date → CAGR=None + warning | Not in §16.2 |
| 7 | `test_drawdown_consistency_gross_net` | Gross and net drawdown methodology consistent (<1.5 diff) | Not in §16.2 |
| 8 | `test_cost_model_fallback_and_retro_intraday` | 2 trades: overnight delivery + same-session intraday with retro fee | Not in §16.2 |
| 9 | `test_entry_fee_accounting_and_retro_refund` | Gross-positive but net-negative trade; fee-inclusive cost basis; same-session fee correction | Not in §16.2 |
| 10 | `test_cagr_scenarios` | CAGR formula: 2yr doubling = 41.42%; insufficient period = None; non-positive equity = None | Not in §16.2 |
| 11 | `test_equity_curve_timestamps` | Intraday uses ISO timestamps; full curve not truncated | Not in §16.2 |

### 12.2 FEAT-008 §16.2 coverage gap analysis

| §16.2 test | Existing coverage | Action |
| :--- | :--- | :--- |
| #1 `test_legacy_mode_byte_identical` | **NOT covered** — no LEGACY mode exists yet | **Must write** (master plan task 1.5) |
| #2 `test_entry_next_bar_open` | Covered by test #1 (next-day-open) | Extend for `execution_model=REALISTIC` explicit |
| #3 `test_exit_signal_next_bar` | Covered by test #1 (exit at open[T+1]) | Extend for explicit mode |
| #4 `test_stop_gapdown_fills_at_open` | **NOT covered** — no stop logic exists | **Must write** (requires new intrabar logic) |
| #5 `test_stop_intrabar_fills_at_stop` | **NOT covered** — no stop logic exists | **Must write** |
| #6 `test_target_gapup_fills_at_open` | **NOT covered** — no target logic exists | **Must write** |
| #7 `test_conservative_stop_before_target` | **NOT covered** — no stop/target ordering exists | **Must write** (most intricate new logic) |
| #8 `test_missing_next_bar_skips` | **NOT covered** — no skip logic exists (end-of-data force-closes instead) | **Must write** (requires `skip_on_missing_next_bar`) |
| #9 `test_nan_open_skips` | **NOT covered** | **Must write** |
| #10 `test_costs_reduce_pnl` | Covered by test #1 (net < gross) | Already covered |
| #11 `test_determinism_two_runs` | **NOT explicitly covered** | **Must write** |
| #12 `test_no_propagation_on_exception` | **NOT covered** — orchestrator catches backtest exceptions (`orchestrator_agent.py:530-544`) but no per-trade exception boundary | **Must write** |
| #13 `test_causality_no_same_bar_fill` | **NOT explicitly covered** — test #1 implies it | **Must write** (explicit assertion) |
| #14 `test_metric_sample_floor` | **NOT covered** — `_empty_result` returns verdict="insufficient" for <35 candles, but no sample-floor test for trade count | **Must write** (or verify existing behavior) |
| #15 `test_cost_components_sum_correctly` | Partially covered by test #4 | Extend for `feat008_total_cost_bps_per_side` |

### 12.3 Other unit tests touching backtest

| Test file | Scope | Relevance |
| :--- | :--- | :--- |
| `backend/tests/unit/test_recommendation_service.py` | 4 tests on `calculate_dynamic_weights` (standard vs catalyst regime) | Validates backtest weight (0.25/0.20); must remain green |
| `backend/app/tests/test_walk_forward.py` | Tests `WalkForwardService._simulate_backtest` with regime gating | Separate path; **Needs Verification** on whether switch propagates here |
| `backend/app/tests/test_sector_rs_overlay.py` | Constructs a `BacktestResult` with `total_return=12.5` as test fixture (`test_sector_rs_overlay.py:202-205`) | Uses `BacktestResult` schema — must remain valid if fields are added |
| `backend/app/tests/test_market_permission.py` | Constructs a `BacktestResult` with `total_return=15.0` as test fixture (`test_market_permission.py:359-362`) | Same — schema extension must not break fixture construction |

---

## 13. Integration Tests Already Available

### 13.1 Orchestrator integration — `backend/tests/integration/test_orchestrator_integration.py`

| Test | What it exercises | Backtest relevance |
| :--- | :--- | :--- |
| `test_orchestrator_service_integration` | End-to-end `OrchestratorAgent.run_full(request)` with mocked FYERS (250 candles), mocked news/sentiment/fundamentals. Asserts `len(response.items)==1`, technical score > 0, fundamental score > 0, `AnalysisHistory` row persisted. | **Exercises the real `BacktestService.run()`** (not mocked). The 250 mock candles pass the <35 candle floor. The backtest result feeds the real `RecommendationService.build()`. This is the closest thing to an integration test for the backtest→composite path. |

### 13.2 Test infrastructure

| Component | Location | Details |
| :--- | :--- | :--- |
| Root conftest | `backend/tests/conftest.py` | SQLite test DB (WAL mode), `TestClient`, per-test log files, `db_session` fixture, `test_settings` autouse fixture (sets `nifty500_symbols`) |
| App conftest | `backend/app/tests/conftest.py` | Async fixtures; `initialize_db` runs Alembic `upgrade head` at session start; `test_client` (httpx ASGITransport); `check_leaks` autouse (fails on leaked tasks/sessions) |
| pytest markers | `pytest.ini` (root) | `unit`, `integration`, `live`, `slow`, `asyncio`, `concurrency`, `soak`, `recovery` |
| Test DB | `tests/artifacts/backend/test_app_v2.db` | SQLite, dropped and recreated per test via `test_engine` fixture |

### 13.3 What FEAT-008 must add (integration)

Per master plan §6 and spec §16.2 test #1:
- **`test_legacy_mode_byte_identical`** (integration, Stage 9): with `execution_model = LEGACY` (or `REALISTIC` preserving today's behavior per ADR), full scan output byte-identical to pre-FEAT-008. This is the **non-negotiable regression gate** (master plan §15.2).
- **Shadow-mode log completeness**: with `execution_model = REALISTIC` + `composite_uses_realistic = false`, both metric sets present in log; no exception propagates.

**Needs Verification** on the exact byte-identity baseline: since Pass 2 already feeds the composite, "pre-FEAT-008" = today's behavior = `execution_model = REALISTIC` + `composite_uses_realistic = true`. The LEGACY-mode test must assert Pass 1 (gross) output equals today's `gross_*` fields, not today's `total_return`.

---

## 14. Potential Regression Risks

| # | Risk | Likelihood | Impact | Evidence | Mitigation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| R1 | **Default `execution_model = LEGACY` silently flips composite from Pass 2 (realistic) to Pass 1 (gross).** This is the #1 risk. The composite already uses `total_return` (Pass 2). Defaulting to LEGACY per spec §13 would change every recommendation. | High (if spec-literal) | High (global score shift) | ADR-001 §9; `orchestrator_agent.py:566`; `recommendation_service.py:64` | Default `execution_model = REALISTIC` (ADR-001 §7 Option B). Byte-identity test asserts `total_return` still feeds composite. |
| R2 | **End-of-data `TEMPORARY_ASSUMPTION`** — open positions force-closed at `final_row["close"]` (close[T]), a residual non-causal edge case. | Present | Low (few trades affected) | `backtest_service.py:458-498` | Audit warning-log volume; decide fix (skip per spec §9.4) or document. Master plan §6 task notes this. |
| R3 | **Conservative stop-before-target intrabar ordering does not exist.** Spec §9.3 requires it; current exit is signal-based only (EMA/MACD/RSI). Adding it is **new logic**, not a switch. | Certain (gap) | Medium (new code path) | `backtest_service.py:443-456` — only `exit_signal`; no stop/target variables | Implement behind `conservative_exit_ordering = true` config (spec §13). Master plan §6 task 1.6. |
| R4 | **`WalkForwardService._simulate_backtest` shares realism utilities.** If `calculate_transaction_costs` or `COST_SCENARIOS` signatures/contents change, this separate validation path is affected. | Medium | Medium | `walk_forward_service.py:13` | Keep `calculate_transaction_costs` and `COST_SCENARIOS` signatures unchanged. **Needs Verification** on whether the switch propagates to walk-forward. |
| R5 | **Schema extension breaks test fixtures.** `test_sector_rs_overlay.py:202` and `test_market_permission.py:359` construct `BacktestResult` directly. Adding required (non-optional) fields would break them. | Low | Low | `test_sector_rs_overlay.py:202-205`; `test_market_permission.py:359-362` | Add `feat008_*` fields with defaults (optional / `None`), per existing pattern (`gross_*` are `None`-able). |
| R6 | **`skip_on_missing_next_bar` changes trade count for short-history stocks.** Skipping the last-bar trade reduces sample size, potentially dropping a stock below the sample floor (verdict="insufficient"). | Medium | Low | `backtest_service.py:181` (`<35` floor); `recommendation_service.py:194` (`trade_count < 5` → 0 component) | Log `trades_skipped`; spec §15 says "sample-size floor enforced, stocks below floor score 0 (existing behavior preserved)". |
| R7 | **Retro-intraday fee logic breaks if exit path is restructured.** The same-session detection (`backtest_service.py:377-392`) depends on `net_position_entry_date` and `exit_date`. | Low | Medium | `backtest_service.py:377-392` | Preserve the pending-exit state machine structure; test #8 and #9 guard this. |
| R8 | **LEGACY byte-identity is ambiguous.** "Pre-FEAT-008" behavior runs Pass 2 as the composite source. If LEGACY = "Pass 1 only", that is NOT today's behavior. If LEGACY = "today's behavior", it is Pass 2. | Certain (ambiguity) | High (invalidates the regression gate) | ADR-001 §4, §9; master plan §6 task 1.5 | **Needs Verification** — System Owner resolves via ADR-001. Recommended: LEGACY = Pass 1 (gross) for shadow comparison; default = REALISTIC = Pass 2 = today. |
| R9 | **`composite_uses_realistic` gate at orchestrator line 566/705.** The orchestrator selects `best_backtest = max(backtests, key=item.total_return)` and persists `backtest_score=backtest.total_return`. In shadow mode, it must select by `gross_total_return` instead — a new code path. | Medium | Medium | `orchestrator_agent.py:566, 705` | Add the gate as a config-driven selection between `total_return` and `gross_total_return`. Test both paths. |
| R10 | **No per-trade exception boundary.** Spec §9.4 constraint 5 requires per-trade try/except (degrade to skip/legacy, never raise). Current code has an agent-level try/except (`orchestrator_agent.py:530-544`) but no per-trade boundary inside the loop. | Low | Medium | `backtest_service.py:326-456` (no try/except in loop); `orchestrator_agent.py:530-544` (agent-level only) | Add per-trade try/except inside Pass 2 loop. Spec §16.2 test #12 validates. |

---

## 15. Recommended Implementation Order

Per `IMPLEMENTATION_MASTER_PLAN.md` §6 (Phase 1 tasks) and ADR-001 §8 (Option B migration), ordered to preserve behavior at every step:

| Step | Task | Done when | Risk addressed |
| :--- | :--- | :--- | :--- |
| **0** | **Confirm ADR-001 Option B with System Owner.** Default `execution_model = REALISTIC` (not LEGACY) and `composite_uses_realistic = true` (not false), because Pass 2 already feeds the composite. This is the D1 decision. | Decision recorded in decision log. | R1, R8 |
| 1 | Add `feat008` config section to `settings.py` with defaults `enabled=true`, `execution_model="REALISTIC"`, `composite_uses_realistic=true`, `cost_scenario="BASE_COST"`, `conservative_exit_ordering=true`, `skip_on_missing_next_bar=true`. | Config present; `.env` overrides work. | — |
| 2 | Add `execution_model: Literal["LEGACY","REALISTIC"]` param to `BacktestService.run()` (default `"REALISTIC"`) and pass-through in `BacktestAgent.run()`. **Do not change any existing default behavior yet.** | Signature present; existing 11 tests still green (default = today's behavior). | R1 |
| 3 | Route the switch: `LEGACY` → return Pass 1 (gross) metrics as the primary `total_return`/`win_rate`/etc.; `REALISTIC` → return Pass 2 as primary (today's behavior), Pass 1 retained as `gross_*`/`legacy_*` for shadow delta. Both passes still run (dual-reporting preserved). | `execution_model=REALISTIC` output == today's output byte-identical. `execution_model=LEGACY` output == today's `gross_*` fields promoted to primary. | R8 |
| 4 | Add `feat008_*` fields to `BacktestResult` schema (all optional / `None`-defaulted). Populate them in `BacktestService.run()` per spec §12.2. | New fields present; existing schema consumers unaffected; `test_sector_rs_overlay.py` and `test_market_permission.py` fixtures still construct valid `BacktestResult`. | R5 |
| 5 | Implement `composite_uses_realistic` gate at `orchestrator_agent.py:566` and `:705`. When `false`, select best backtest by `gross_total_return` and persist `backtest_score = gross_total_return`. When `true` (default), today's behavior unchanged. | Gate present; default `true` = today's behavior; `false` = composite uses gross. | R9 |
| 6 | **Write `test_legacy_mode_byte_identical`** (integration, Stage 9 gate). Assert `execution_model=REALISTIC` + `composite_uses_realistic=true` produces byte-identical output to pre-FEAT-008 (today's behavior). Assert `execution_model=LEGACY` produces Pass 1 metrics as primary. | Test passes; regression gate in place. | R1, R8 |
| 7 | **Verify conservative intrabar stop-before-target ordering** (spec §9.3). Current exit is signal-based only — **this is a gap**. If the strategy does not track stop/target levels, decide: (a) add stop/target tracking + conservative ordering behind `conservative_exit_ordering=true`, or (b) document that the current signal-based exit is the intended model and the spec's stop/target ordering applies only when stops/targets are configured. | Gap documented or logic implemented behind flag. | R3 |
| 8 | Implement `skip_on_missing_next_bar=true` for the end-of-data edge case (spec §9.4 constraint 5). Replace the `TEMPORARY_ASSUMPTION` force-close with a skip + log when the next bar is unavailable. Keep the force-close as fallback when `skip_on_missing_next_bar=false`. | End-of-data trades skipped (not force-closed) when flag is true; logged. | R2, R6 |
| 9 | Add per-trade try/except boundary inside the Pass 2 loop (spec §9.4 constraint 5; spec §15). Degrade to skip or legacy fill; never raise into the agent path. | Per-trade exception logged and skipped; `test_no_propagation_on_exception` passes. | R10 |
| 10 | Extend the realism test suite with FEAT-008 §16.2 cases not already covered (see §12.2 gap table): #1 (legacy byte-identity), #4-#9 (stop/target/skip), #11 (determinism), #12 (no-propagation), #13 (causality), #14 (sample floor), #15 (cost sum). | All new tests green; existing 11 tests green. | All |
| 11 | Run full historical scan in `LEGACY` vs `REALISTIC`-shadow (`composite_uses_realistic=false`); compare per spec §16.3. Record mean P&L reduction, win-rate reduction, profit-factor reduction, label-distribution shift. | Comparison report generated; metrics within §16.3 targets. | — |
| 12 | **Conditional** — if `feat008_execution_model` / `feat008_score_used` must persist, add 2 nullable columns to `BacktestHistory` + idempotent Alembic migration. Master plan §12 says "likely none" — the 10 realism columns already exist. | Migration applied and downgraded cleanly. | R4 (if walk-forward also needs it) |
| 13 | **Needs Verification** — decide whether `WalkForwardService._simulate_backtest` gets the `execution_model` switch. It is a separate validation path that does not feed recommendations. | Decision recorded. | R4 |

### Ordering rationale

Steps 1-5 are **behavior-preserving** — they add plumbing with defaults that reproduce today's exact behavior. Step 6 locks in the regression gate before any logic changes. Steps 7-9 add the spec-required logic that does not yet exist (stop/target ordering, skip-on-missing, per-trade exception boundary). Step 10 validates. Steps 11-13 are validation and verification.

This ordering ensures that at every commit, the system is in a deployable state with today's behavior preserved.

---

## Constraints Acknowledged

- **No code generated** in this report.
- **No architecture redesigned** — this report analyzes the existing repository only.
- **No services rewritten** — existing utilities are identified for reuse.
- **No new runtime components suggested** — FEAT-008 is a bounded delta to `COMP-BT` only.
- **Repository evidence only** — every claim cites a file and line number.
- **Unknowns marked "Needs Verification"** — D1 default value, cost-config mapping, walk-forward propagation, stop/target gap.

---

## Summary of Key Findings

1. **The FEAT-008 realism layer is ~85% implemented and already live.** `BacktestService.run()` already runs causal next-bar-open execution (Pass 2), full Indian cost stack, slippage (3 tiers), position sizing, gross/net dual reporting, and DB persistence (10 columns, migrated).

2. **The composite already uses the realistic metric.** `total_return` (Pass 2) feeds the composite via `orchestrator_agent.py:566` and `recommendation_service.py:64`. `gross_total_return` (Pass 1) is persisted but does not feed scoring. **D1 is resolved: Pass 2 = today's composite source.**

3. **The missing 15% is selectability and naming, not realism math.** No `execution_model` switch, no `composite_uses_realistic` flag, no `feat008` identifiers exist. Adding them is a small plumbing delta.

4. **Two gaps require new logic (not just a switch):** (a) conservative intrabar stop-before-target ordering (spec §9.3 — currently absent); (b) `skip_on_missing_next_bar` for the end-of-data `TEMPORARY_ASSUMPTION` edge case.

5. **The #1 risk is the default.** Defaulting `execution_model = LEGACY` (spec §13) would flip the composite to Pass 1 — a silent global behavior change. ADR-001 §7 recommends default `REALISTIC` to preserve today's behavior.

6. **11 realism unit tests + 1 orchestrator integration test already exist** and must remain green. The FEAT-008 §16.2 suite adds ~10 new test cases (conservative ordering, skip, determinism, no-propagation, causality, sample floor).

7. **A separate validation backtest path exists** (`WalkForwardService._simulate_backtest`) that imports the realism utilities. It does not feed recommendations. **Needs Verification** on switch propagation.

---

*End of FEAT008_IMPLEMENTATION_ANALYSIS.md*
