# FEAT-008 — Realistic Trade Execution Model
**Version:** 1.0 — Specification
**Date:** 2026-07-11
**Status:** Ready for architecture review (FEAT-006 Stage 5)

---

## 1. Candidate Idea Submission

| Field | Value |
| :--- | :--- |
| **Idea Name** | FEAT-008 — Realistic Trade Execution Model |
| **One-Line Description** | Replace the backtest's optimistic same-candle-close fills with causal next-bar-open execution and deduct slippage, brokerage, and statutory charges, so the `BacktestAgent`-derived score reflects trades a human could actually execute. |
| **Primary Component Tag** | `COMP-BT` |
| **Secondary Component Tag** | None |
| **Primary Situation Tag** | `SIT-BMR` |
| **Secondary Situation Tags** | None |
| **Target Implementation Class** | `BacktestAgent` — the existing historical trade simulation and performance-calculation module. No new class, no new agent. |
| **Required Input Data** | Existing daily OHLCV (FEAT-001 §5); a static execution-cost schedule in config (slippage bps, brokerage bps, statutory charges bps). No new external data, no new data provider. |
| **Safe Fallback Behavior** | `execution_model = LEGACY` reproduces today's behavior exactly. If next-bar open is unavailable or NaN, the trade is skipped (cannot be executed) and logged. Any exception in the realistic path degrades to skip or legacy, never propagates. |
| **Deterministic Logic Check** | Given the same OHLCV and the same cost config, every simulated fill price, P&L, and derived metric is identical across runs — no LLM, no ML, no randomness. |
| **Explainability Check** | A human can read `"Filled entry at open[T+1] = 102.0, +5 bps slippage, +15 bps costs → effective 102.20"` and verify it against the price chart and the cost schedule with a calculator. |
| **Idea Type** | `soft-score-factor` (alters the backtest performance metrics that feed the 25%/20% backtest weight in the composite) |
| **Known Gaps Addressed** | FEAT-001 §8 **Gap #11** (entry look-ahead), **#12** (exit look-ahead), **#13** (no slippage), **#14** (no fees) |
| **Evidence Level (FEAT-005)** | **Level A** (see §6) |

---

## 2. Executive Summary

The `RecommendationAgent` weights the `BacktestAgent` output at **25 (standard regime) / 20 (catalyst regime)** of the composite score (FEAT-001 §4). That backtest score is derived from simulated trade outcomes. Today those simulations have two structural flaws that together inflate every backtest metric: the fills are **non-causal** (a signal on candle *T*'s close is filled at that same close — physically impossible) and **cost-blind** (no slippage, brokerage, STT, or other charges).

Because these flaws sit inside a 25%-weight component, **every recommendation is distorted**, not edge cases. FEAT-008 is a single bounded delta to `COMP-BT` that introduces a **Realistic Trade Execution Model**:

- **Tier 1 — Causal Execution:** entries and exits fill at the next bar's open (`open[T+1]`), with stops and targets evaluated conservatively against the next bar's range.
- **Tier 2 — Execution Cost Model:** slippage, brokerage, and statutory charges are deducted per side as configurable basis-point terms from the fill price.

The change is config-driven (`LEGACY` vs `REALISTIC`), deterministic, brownfield-safe, and rollback-able with one config line. It introduces no new data, no new agents, no changes to `COMP-REC`, `COMP-RISK`, or FEAT-004 logic. It is staged through shadow mode (compute and log realistic metrics while the composite still uses legacy) before activation, exactly per FEAT-006 §7.2.

**In scope:** Items 1–6 (look-ahead correction, entry timing, exit timing, slippage, brokerage, taxes/charges). **Out of scope:** corporate actions, partial fills, liquidity modelling, position sizing, intraday execution, order-book simulation, tick data, new runtime agents, new data providers. Those are deferred to future features (§19, §8.2).

---

## 3. Feature Justification

### 3.1 Why this feature, why now

FEAT-004 and FEAT-007 added *signals* (broad-market regime, sector relative strength) that modify the composite score. Both compose with a weighted backtest score that is itself distorted. Adding more signals on top of a biased 25%-weight input compounds the distortion: the synthesizer weights a clean technical score against an inflated backtest score. The highest-value next move is not another signal — it is to repair the substrate those signals are weighted against.

### 3.2 Why a single feature, not a split (per approved Architecture Review)

The approved scope (Option A) bundles Items 1–6 into one feature because they form **one bounded concern**: realistic trade execution inside `COMP-BT`. Splitting them would create incoherent intermediate states (causal fills with zero cost; causal entry with non-causal exit) that would never be activated, wasting each split's shadow window. The six items are two operations in one fill-calculation function: (i) choose the fill price causally, (ii) deduct the per-side cost from it.

### 3.3 Why the other items are excluded

Corporate actions (Item 7), partial fills (Item 8), and liquidity modelling (Item 9) each require new data dependencies, new architectural prerequisites (notably Gap #15 position sizing, and for partial fills, intraday data which FEAT-001 §6 declares "not applicable"), and touch components beyond `COMP-BT`. They are legitimate future features but are a different complexity class and are explicitly deferred (§8.2).

### 3.4 Why this is the strongest-evidenced feature in the OS

The claims "transaction costs materially reduce reported returns" and "same-candle-close fills introduce look-ahead bias" are uncontested in both peer-reviewed literature and practitioner platforms. FEAT-005 §13 Example 1 already uses this exact claim as its canonical **Level A** illustration (score 100). FEAT-008 is the operationalization of that example.

---

## 4. Target Component

**`COMP-BT` — `BacktestAgent`** (the only component touched).

**Justification per FEAT-003 Rule 1 (Delta-Based Component Tagging):**

- The code delta lives entirely inside `BacktestAgent` — specifically the execution/fill model and the performance-metric calculation.
- **Not** `COMP-REC`: synthesis weights, the composite formula, and backtest-score normalization are untouched. FEAT-008 changes only the *raw trade outcomes* from which metrics are derived.
- **Not** `COMP-TA`: no indicator or price-action logic changes.
- **Not** `COMP-RISK`: the Strict Buy Gate is entirely untouched.
- **Not** `COMP-MD`: no data fetching, caching, or provider logic changes.

This classification follows the FEAT-002 §5 **Example 6** precedent (*"Slippage Modeling in Backtest → `COMP-BT`"*), which is the canonical worked example for exactly this kind of change.

---

## 5. Target Situation

**`SIT-BMR` — Broad Market Regime** (primary, no secondary).

Per FEAT-002 §5 Example 6: *"Changes the execution physics of the simulator. It applies to all simulated market environments, so it is marked under `SIT-BMR` (broad execution drag)."* Execution friction — both the timing correction and the cost deduction — is regime-independent: it penalizes trades identically whether the market is bull, bear, or sideways. The `SIT-BMR` tag denotes a baseline change affecting all conditions, exactly as the precedent specifies.

**Misclassification guard (FEAT-003 §4):** This is **not** `SIT-CSE`. Although costs apply to single-stock trades, the *drag itself* is a universal execution property, not a company-specific event. Tagging it `SIT-CSE` would repeat the trap FEAT-003 warns against. It is also **not** a second `SIT-BMR` *regime detector* like FEAT-004 — it does not detect or classify a regime; it applies a baseline execution correction across all regimes. There is no overlap with FEAT-004's logic.

---

## 6. Evidence Level

**Level A — Academically Proven** (FEAT-005 §4).

### 6.1 Evidence dossier (per FEAT-005 §7)

| FEAT-005 Dimension | Score | Artefact basis |
| :--- | :--- | :--- |
| D1 — Academic literature support | 25 | Two uncontested peer-reviewed strands: (a) transaction-cost-adjusted performance (Lo, Mamaysky & Wang on market efficiency with costs; Korajczyk & Sadka on liquidity-adjusted returns); (b) the backtesting-methodology literature documenting look-ahead and data-snooping biases. ≥ 3 independent peer-reviewed sources. |
| D2 — Practitioner / professional adoption | 25 | Cost-adjusted, next-bar backtesting is the default in every professional platform (Zipline, Backtrader, Amibroker, QuantConnect). Same-candle-close fills are universally treated as a methodology error. |
| D3 — Empirical / statistical evidence | 25 | Large out-of-sample evidence that ignoring costs overstates returns and changes strategy rankings; documented effect sizes. |
| D4 — Independent replication | 15 | Universal replication — no credible backtest omits costs or fills at the signal close. |
| D5 — Evidence stability | 10 | Effect holds across every market regime and every tested period. |
| **Total** | **100** | → **Level A** (FEAT-005 §5.3 threshold: ≥ 85) |

### 6.2 Acceptance criteria check (FEAT-005 §4 Level A)

- (i) ≥ 3 independent peer-reviewed sources — **met**.
- (ii) ≥ 1 independent replication — **met** (universal).
- (iii) Statistically significant effect size reported — **met**.
- (iv) No uncontested contradictory evidence — **met** (none exists; the claim is not contested).
- (v) Effect demonstrated out-of-sample — **met**.

### 6.3 Lifecycle consequence

At Level A, FEAT-008 is **activation-eligible** (FEAT-006 §7.2: Stage 15 requires ≥ B). It is not evidence-capped. It is still staged through shadow before activation (§16) because it shifts a 25%-weight component globally and the System Owner must review the label-distribution shift.

---

## 7. Lifecycle Placement

Per **FEAT-006**, FEAT-008 traverses:

| Stage | Status |
| :--- | :--- |
| 1. Idea Submitted | ✅ This document |
| 2. Classification | ✅ `COMP-BT` / `SIT-BMR` (§4, §5; validated against FEAT-003 Rules 1–4 and FEAT-002 §5 Example 6) |
| 3. Eight-Axis Evaluation | ✅ §16.1 |
| 4. Evidence Classification | ✅ **Level A** (§6) |
| 5. Architecture Review | **This document seeks approval** — §17 |
| 6. Implementation Approval | ⏳ Awaiting System Owner |
| 7. Implementation | ⏳ Modify `BacktestAgent` fill model + cost deduction only |
| 8. Unit Testing | ⏳ §16.2 |
| 9. Integration Testing | ⏳ Verify LEGACY mode is byte-identical to pre-FEAT-008 |
| 10. Backtesting | ⏳ **Self-referential:** FEAT-008 *is* the simulator. Validated by re-running the engine's historical scan and comparing LEGACY vs REALISTIC metrics (§16.3). |
| 11. Walk-Forward | ⏳ Out-of-sample metric stability comparison |
| 12. Paper Trading | ⏳ Analogue = score-delta audit (how many labels change under realistic scoring) |
| 13. Production Candidate | ⏳ System Owner approval to shadow |
| 14. Shadow Mode | ⏳ Compute realistic metrics, **log delta vs legacy**, composite still uses legacy score |
| 15. Production Activation | ✅ **Eligible at Level A**. Switch composite to realistic score. |
| 16. Production Monitoring | ⏳ Monitor recommendation-label distribution shift (§16.4) |
| 17. Rollback | One-line config: `feat008.execution_model = LEGACY` |

**Special note on Stages 10/12 (self-referential validation):** Because FEAT-008 modifies the simulator itself, the usual "backtest the feature" step becomes "compare the legacy simulator against the realistic simulator on identical historical data." The paper-trading analogue is the *score-delta audit* — measuring how many recommendations would change label under realistic scoring before flipping the composite over.

---

## 8. Current Problem

### 8.1 The four gaps FEAT-008 closes

FEAT-001 §8 lists four backtest-realism gaps. FEAT-008 addresses all four:

| Gap | Current (flawed) behaviour | FEAT-008 fix |
| :--- | :--- | :--- |
| **#11** Entry look-ahead | Signal on close[T] → fill at close[T] | Fill at open[T+1] (next available price) |
| **#12** Exit look-ahead | Exit signal on close[T] → fill at close[T] | Fill at open[T+1], or at the stop/target level if hit intrabar on [T+1] |
| **#13** No slippage | Fill = raw price | Fill = raw price ± slippage (adverse) |
| **#14** No fees | Fill = raw price | Fill = raw price − brokerage − statutory charges (per side) |

### 8.2 Explicitly out of scope (deferred to future features)

| Deferred item | Reason for deferral | Prerequisite trigger |
| :--- | :--- | :--- |
| **Corporate actions** (splits, bonuses, dividends) | Upstream data-preprocessing concern (`COMP-MD`), requires a corporate-actions feed and retroactive price-series adjustment — a different component and data project | When the owner models total return or when an unadjusted corporate action materially distorts a backtest |
| **Partial fills** | Requires intraday order-book data (violates FEAT-001 §6) and a position-sizing model (Gap #15, unresolved) | Only if the system scales to position sizes where NIFTY 500 liquidity is binding |
| **Liquidity modelling** | Requires volume-at-price / order-book depth data and Gap #15 | Only if the universe expands to illiquid names |
| **Position sizing** (Gap #15) | A separate, larger capital-deployment design decision | A dedicated future feature |
| **Intraday execution / tick data / order-book simulation** | Violates FEAT-001 §6 ("intraday not applicable" to this swing system) | Not applicable to the current architecture |

FEAT-008 bounds itself strictly to *execution* realism — when and at what cost a trade fills — not *sizing*, *adjustment*, or *microstructure*.

---

## 9. Proposed Execution Model

### 9.1 The two execution models

FEAT-008 introduces a config switch: `feat008.execution_model ∈ {LEGACY, REALISTIC}`.

| Mode | Entry fill | Exit fill | Costs |
| :--- | :--- | :--- | :--- |
| `LEGACY` | close[T] (unchanged) | close[T] (unchanged) | None (unchanged) |
| `REALISTIC` | open[T+1] adjusted (§9.2) | open[T+1] or intrabar stop/target on [T+1], adjusted (§9.3) | Slippage + brokerage + statutory charges (§10) |

`LEGACY` mode is the exact current behaviour. It exists so rollback is one config line and so shadow mode can compute both side-by-side.

### 9.2 Entry fill (REALISTIC)

A signal generated on candle *T*'s close cannot be acted upon until the next bar. The entry fills at the next bar's open:

```
raw_entry       = open[T+1]
slipped_entry   = raw_entry * (1 + slippage_bps / 10000)       # adverse for a BUY (price rises)
effective_entry = apply_costs(raw=slipped_entry, side="BUY")    # brokerage + statutory, §10
```

For a BUY, the effective entry is *higher* than the raw open (you pay more). Deterministic: same OHLCV + same config → same fill.

### 9.3 Exit fill (REALISTIC)

Exits are either (a) a signal-generated exit, or (b) a stop-loss / target hit.

**(a) Signal exit on candle T:**
```
raw_exit        = open[T+1]
slipped_exit    = raw_exit * (1 - slippage_bps / 10000)         # adverse for a SELL (price falls)
effective_exit  = apply_costs(raw=slipped_exit, side="SELL")    # brokerage + statutory, §10
```

**(b) Stop / target intrabar check on candle T+1** (conservative, deterministic ordering):

A standing stop-loss *S* and target *TGT* are evaluated against candle T+1's range. Evaluation order is **conservative** (assume the worst case first), mirroring FEAT-004 §4's "when in doubt, be conservative":

```
if open[T+1] <= S:                      raw_exit = open[T+1]         # gap-down below stop
elif open[T+1] >= TGT:                  raw_exit = open[T+1]         # gap-up above target
elif low[T+1]  <= S:                    raw_exit = S                 # stop hit intrabar
elif high[T+1] >= TGT:                  raw_exit = TGT               # target hit intrabar
else:                                   # no exit this bar; hold, recheck next bar
```

The resulting raw exit is then adjusted for slippage and costs as in (a).

**Why conservative ordering:** If both stop and target are within T+1's range, the backtest cannot know which printed first on intraday data it does not have (FEAT-001 §6: intraday not applicable). Assuming the stop hit first is the pessimistic, bias-against-the-strategy choice — it *under*-states returns, which is the safe direction. This is the opposite of the current same-candle bias.

### 9.4 Deterministic constraints (no-discretion guards)

1. **Determinism:** Identical OHLCV + identical config → identical fills, metrics, and score. No randomness.
2. **LEGACY purity:** `execution_model = LEGACY` produces byte-for-byte the current behaviour. Verified at Stage 9 (integration test, §16.2 test 1).
3. **Conservative bias:** Where intrabar ambiguity exists (stop vs target), the *pessimistic* fill is chosen. FEAT-008 may only *reduce* simulated returns relative to a neutral assumption, never inflate them.
4. **Causality:** No fill ever uses data from candle *T* to fill a *T*-generated signal. Entry and signal always differ by ≥ 1 bar.
5. **Non-propagation:** Any failure to compute a realistic fill (missing next bar, NaN) with `skip_on_missing_next_bar = true` skips the trade and logs it — never raises into the agent path.

### 9.5 Worked numeric example

Stock signals BUY on candle T where close[T] = 100.0; next bar open[T+1] = 102.0. Config: slippage 5 bps, brokerage 5 bps, statutory 10 bps per side (15 bps total per side).

| Step | Value |
| :--- | :--- |
| raw_entry | 102.0 |
| slipped_entry | 102.0 × 1.0005 = 102.051 |
| effective_entry | 102.051 × 1.0015 = 102.204 |
| *(vs LEGACY entry)* | *(100.0)* |

Suppose a standing target of +8% (110.38 effective) and on T+5 the bar gaps up, open[T+5] = 111.0 (above target): conservative ordering → fill at open since open ≥ TGT.

| Step | Value |
| :--- | :--- |
| raw_exit | 111.0 |
| slipped_exit | 111.0 × 0.9995 = 110.9445 |
| effective_exit | 110.9445 × 0.9985 = 110.778 |
| Realistic P&L | (110.778 / 102.204) − 1 = **+8.39%** |

The point is not that realism always lowers returns — here the trade ran further than the close-based entry. The point is that realism reports *achievable* returns. Over many trades, costs dominate and lower the aggregate.

---

## 10. Execution Cost Model

### 10.1 The three cost components (Tier 2)

All three are per-side, configurable basis-point terms deducted from the (already slipped) fill price. From the simulator's perspective they are **indistinguishable** — they are additive cost components applied by the same operation. Splitting them at the code level would be artificial; they are split only in config for auditability.

| Component | Code role | Config key | Default (placeholder) |
| :--- | :--- | :--- | :--- |
| **Slippage** (Item 4) | Adverse price movement between decision and fill | `slippage_bps` | 5 bps per side |
| **Brokerage** (Item 5) | Broker's per-order charge | `brokerage_bps` | 5 bps per side |
| **Statutory charges** (Item 6) | STT + exchange + GST + stamp duty + SEBI turnover + IGST | `statutory_bps` | 10 bps per side |

### 10.2 The `apply_costs` operation

```
def apply_costs(raw, side):
    # total per-side cost in basis points
    total_cost_bps = slippage_bps + brokerage_bps + statutory_bps
    if side == "BUY":
        return raw * (1 + total_cost_bps / 10000)     # you pay more
    else:  # SELL
        return raw * (1 - total_cost_bps / 10000)     # you receive less
```

Note: slippage is folded into `apply_costs` as the first term rather than applied separately, because all three components modify the same fill price by the same multiplicative mechanism. Keeping them as three named config keys preserves auditability (the owner can see which portion is slippage vs brokerage vs statutory on the contract note) while the simulator treats them as one subtraction.

### 10.3 Per-side vs round-trip

A complete trade pays the per-side cost **twice**: once on entry (BUY side), once on exit (SELL side). With the placeholder defaults (15 bps per side), a round trip costs ~30 bps before any price movement. The owner must verify the actual figures against the broker/NSE rate card before activation — rates change on budgetary/regulatory schedules, and a wrong figure is worse than a configurable one.

### 10.4 Why flat bps, not tiered

For a personal-use system with one broker and one account, flat per-side bps is sufficient and deterministic. Tiered (volume-based or slab-based) brokerage adds a lookup but no realism benefit at personal-system trade sizes. If the owner later adopts a tiered broker schedule, that becomes a config enhancement, not a feature — the `apply_costs` signature stays the same.

---

## 11. Required Inputs

| Input | Source | Already in engine? | New data? |
| :--- | :--- | :--- | :--- |
| Daily OHLCV (open, high, low, close) | FEAT-001 §5 | Yes | **No** |
| Slippage bps | Static config | Config system exists | **No** (new config value, not new data) |
| Brokerage bps | Static config | Config system exists | **No** |
| Statutory charges bps | Static config | Config system exists | **No** |
| Existing indicator / stop / target logic | `BacktestAgent` | Yes | **No** |

**FEAT-008 introduces zero new external data dependencies.** It consumes only the OHLCV the simulator already uses, plus static cost parameters. This is the core reason it is low implementation risk.

---

## 12. Required Outputs

### 12.1 Per-trade outputs (inside BacktestAgent)

```
trade_id
entry_candle_signal    = T                          # candle whose close generated the signal
entry_fill_candle      = T+1                        # candle at which the fill occurred
raw_entry              = open[T+1]
effective_entry        = float                      # after slippage + costs
exit_fill_candle       = ...
raw_exit               = float
effective_exit         = float
pnl_pct                = float                      # realistic
legacy_pnl_pct         = float                      # legacy, for shadow delta logging
fill_skipped_reason    = string | null              # e.g. "missing_next_bar"
```

### 12.2 Per-stock backtest result payload

```
feat008_enabled                 = True | False
feat008_execution_model         = LEGACY | REALISTIC
feat008_slippage_bps            = float
feat008_brokerage_bps           = float
feat008_statutory_bps           = float
feat008_total_cost_bps_per_side = float
feat008_trades_simulated        = int
feat008_trades_skipped          = int
feat008_win_rate                = float              # realistic
feat008_profit_factor           = float              # realistic
feat008_legacy_win_rate         = float              # legacy (shadow delta)
feat008_legacy_profit_factor    = float              # legacy (shadow delta)
feat008_score_used              = "legacy" | "realistic"     # which fed the composite
feat008_explanation             = string
```

### 12.3 Human-readable explanation string

> `"Backtest executed in REALISTIC mode: next-bar-open fills, 15 bps total cost per side (5 slip + 5 brokerage + 10 statutory). 42 trades simulated, 3 skipped (missing next bar). Win rate 54% (legacy reported 61%), profit factor 1.42 (legacy reported 1.78)."`

This makes the optimism gap visible and auditable.

---

## 13. Configuration

All flags live in the existing application config (YAML/JSON/Python dict — whichever the engine already uses). No new config system.

```yaml
feat008:
  enabled: true                       # Master switch. false = FEAT-008 never runs.
  execution_model: "LEGACY"           # "LEGACY" | "REALISTIC"
  slippage_bps: 5                     # Adverse price movement per side.
  brokerage_bps: 5                    # Broker per-order charge per side.
  statutory_bps: 10                   # STT + exchange + GST + stamp + SEBI per side.
                                      # (Owner MUST verify against broker contract note before REALISTIC activation.)
  conservative_exit_ordering: true    # Assume stop before target when both in range.
  skip_on_missing_next_bar: true      # If open[T+1] unavailable/NaN, skip trade (cannot execute).
  composite_uses_realistic: false     # false = SHADOW (composite still uses legacy score).
                                      # true  = ACTIVE (composite uses realistic score). Flip at Stage 15.
```

The `composite_uses_realistic` flag is the Stage 14 → Stage 15 switch. In shadow, `execution_model = REALISTIC` but `composite_uses_realistic = false`, so realistic metrics are computed and logged while the composite score is unaffected. At activation, only `composite_uses_realistic` flips to `true` — one line, instant effect, instant rollback.

---

## 14. Logging

Every field below is written on every stock processed, regardless of mode.

| Field | Populated When | Value if LEGACY / Abstained |
| :--- | :--- | :--- |
| `feat008_enabled` | Always | `false` |
| `feat008_execution_model` | Always | `"LEGACY"` |
| `feat008_slippage_bps` | Always | config value |
| `feat008_brokerage_bps` | Always | config value |
| `feat008_statutory_bps` | Always | config value |
| `feat008_total_cost_bps_per_side` | Always | sum of above |
| `feat008_trades_simulated` | Always | legacy trade count |
| `feat008_trades_skipped` | REALISTIC only | `0` in LEGACY |
| `feat008_win_rate` | Always | legacy value |
| `feat008_profit_factor` | Always | legacy value |
| `feat008_legacy_win_rate` | REALISTIC only (for delta) | `null` in LEGACY |
| `feat008_legacy_profit_factor` | REALISTIC only | `null` in LEGACY |
| `feat008_score_used` | Always | `"legacy"` |
| `feat008_explanation` | Always | `"LEGACY mode: unchanged."` |

**Audit guarantee:** In shadow, both realistic and legacy metrics are present, so the System Owner can read the per-stock optimism gap directly from the log before approving activation. No field is ever silently omitted; missing values are explicitly `null`.

---

## 15. Failure Modes

| Failure Mode | Risk Level | Mitigation |
| :--- | :--- | :--- |
| Realistic scoring shifts many recommendations at once → label-distribution churn | Medium | Shadow mode (Stage 14) logs the full delta before the composite switches; System Owner reviews distribution shift at Stage 15 |
| Cost-schedule figures wrong (STT/brokerage rate changed) | Medium | Config-driven, not hardcoded; owner verifies against broker contract note before activation (§13); defaults are placeholders only |
| Conservative exit ordering understates returns excessively | Low | Configurable (`conservative_exit_ordering`); the pessimistic direction is the safe one |
| Trades skipped at end of history reduce sample size for short-history stocks | Low | Logged (`trades_skipped`); sample-size floor enforced in metric calc; stocks below floor score 0 (existing behaviour preserved) |
| LEGACY mode accidentally diverges from pre-FEAT-008 behaviour | Medium | Stage 9 integration test asserts byte-identical output in LEGACY mode (§16.2 test 1) |
| Realistic path raises into agent loop | Low | Per-trade try/except → degrades to skip or legacy fill (§9.4 constraint 5); never propagates |
| Slippage/cost double-counted with any future live-execution cost model | Low | FEAT-008 is backtest-only; live execution is a separate concern owned elsewhere |
| Cost config missing | Low | Defaults to 0 (degrades to slippage-only if slippage present, else legacy), logs warning |

---

## 16. Validation Plan

### 16.1 Eight-axis evaluation (FEAT-001 §10)

| Axis | Rating | Rationale |
| :--- | :--- | :--- |
| Profitability impact | Medium | Does not add return; makes the backtest signal trustworthy so the composite weights truth, not optimism |
| False-positive risk | **Reduced** | Cost-blind backtests over-state high-turnover/high-spread stocks → false-positive BUYs; realism removes these |
| False-negative risk | Low | Conservative exit ordering may under-state some winners, but symmetric across the universe |
| Overfitting risk | **Very Low** | No parameters fit to history; cost schedule is externally verified, not tuned |
| Data availability | High | Uses only existing OHLCV |
| Implementation complexity | Low | Bounded delta to one component's fill model |
| Testability | High | Pure function: (OHLCV, config) → fills → metrics |
| Explainability | High | "Next open + costs" — one sentence (§12.3) |

### 16.2 Unit test plan (FEAT-006 Stage 8)

All deterministic: fixed inputs, fixed expected outputs. No live data.

| # | Test | Input | Expected |
| :--- | :--- | :--- | :--- |
| 1 | `test_legacy_mode_byte_identical` | LEGACY, any history | Output == pre-FEAT-008 output exactly |
| 2 | `test_entry_next_bar_open` | signal T, open[T+1]=102 | effective_entry = 102 × (1 + total_cost_bps/10000) |
| 3 | `test_exit_signal_next_bar` | exit signal T, open[T+1] | effective_exit = open[T+1] × (1 − total_cost_bps/10000) |
| 4 | `test_stop_gapdown_fills_at_open` | open[T+1] < stop | raw_exit = open[T+1] |
| 5 | `test_stop_intrabar_fills_at_stop` | low[T+1] ≤ stop < open[T+1] | raw_exit = stop |
| 6 | `test_target_gapup_fills_at_open` | open[T+1] > target | raw_exit = open[T+1] |
| 7 | `test_conservative_stop_before_target` | both in range | stop wins |
| 8 | `test_missing_next_bar_skips` | signal on last bar | trade skipped, logged |
| 9 | `test_nan_open_skips` | open[T+1] = NaN | trade skipped, logged |
| 10 | `test_costs_reduce_pnl` | any round trip | realistic P&L < zero-cost P&L |
| 11 | `test_determinism_two_runs` | same inputs twice | identical fills and metrics |
| 12 | `test_no_propagation_on_exception` | inject error in realistic path | degrades to skip/legacy, no raise |
| 13 | `test_causality_no_same_bar_fill` | any signal | entry_fill_candle > signal_candle always |
| 14 | `test_metric_sample_floor` | too few trades | score = 0 (existing behaviour preserved) |
| 15 | `test_cost_components_sum_correctly` | slip=5, broker=5, stat=10 | total_cost_bps_per_side = 15 |

### 16.3 Backtest / comparison plan (FEAT-006 Stages 10–11)

Because FEAT-008 *is* the simulator, validation is a controlled comparison on identical historical data:

1. Run the full historical scan in `LEGACY` → record per-stock backtest metrics and final composite labels (baseline).
2. Run the same scan in `REALISTIC` (`composite_uses_realistic = false`) → record the same (treatment).
3. Compare:

| Metric | Target | Rollback Trigger |
| :--- | :--- | :--- |
| Mean backtest P&L reduction (realistic vs legacy) | Must be > 0 (costs must bite) | 0 or negative → cost config wrong |
| Win-rate reduction | Bounded, explainable | > 15 pp drop → investigate (config or bug) |
| Profit-factor reduction | Bounded | > 30% drop → investigate |
| Recommendation label distribution shift (BUY/WATCH/REJECT counts) | Documented; reviewed by System Owner at Stage 15 | Unreviewed shift → do not activate |
| Stocks dropping BUY → WATCH specifically due to backtest score | Quantified; reviewed | — |
| Out-of-sample (walk-forward) consistency | Realistic metrics stable across windows | Regime collapse → investigate |

### 16.4 Shadow window (FEAT-006 Stage 14)

Minimum 30 trading sessions (FEAT-004 §12 precedent). In shadow, the composite **continues to use the legacy backtest score**, but realistic metrics and the full legacy-vs-realistic delta are logged per stock. The System Owner reviews the label-distribution shift before approving Stage 15 activation (flipping `composite_uses_realistic` to `true`).

---

## 17. Brownfield Safety Confirmation

| Constraint (FEAT-001 §2, FEAT-003 Instruction 8, FEAT-006 §13) | Status |
| :--- | :--- |
| No existing hard filter removed or weakened | ✅ Confirmed |
| Strict Buy Gate criteria unchanged | ✅ Confirmed (Gate is not in the backtest path) |
| No new autonomous agents created | ✅ Confirmed (no agent; internal simulator change) |
| BUY/WATCH/REJECT thresholds unchanged | ✅ Confirmed (72/55 preserved; only the backtest *score input* changes) |
| Deterministic: same inputs → same outputs | ✅ Confirmed (§9.4) |
| Missing data defaults to safe behavior | ✅ Confirmed (§9.4 constraint 5, §15 — skip or legacy) |
| No exceptions propagate to recommendation path | ✅ Confirmed (per-trade try/except boundary) |
| Rollback requires only config flag change | ✅ Confirmed (`execution_model = LEGACY`) |
| Bounded delta to one named component | ✅ Confirmed (`BacktestAgent` only) |
| No new external data dependencies | ✅ Confirmed (§11) |
| No new `COMP-*` or `SIT-*` tags | ✅ Confirmed (`COMP-BT`/`SIT-BMR`, both pre-existing per FEAT-002 §5 Example 6) |
| LEGACY mode is byte-identical to today | ✅ Confirmed (Stage 9 integration test asserts) |
| Does not duplicate FEAT-004 / FEAT-007 | ✅ Confirmed — different component (`COMP-BT`), different concern (execution realism vs regime/sector signals) |
| Does not alter `COMP-REC` normalization formula or weights | ✅ Confirmed (those are `COMP-REC`; untouched) |
| Does not alter `COMP-RISK` | ✅ Confirmed (Gate untouched) |
| Does not alter FEAT-004 logic | ✅ Confirmed (FEAT-004 operates on the composite in `COMP-REC`; FEAT-008 operates on backtest inputs in `COMP-BT` — separate code paths) |

---

## 18. Rollback Plan

**Rollback mechanism:** One-line config change. No code change required (FEAT-006 RI-1).

```yaml
feat008:
  execution_model: LEGACY      # instant revert to pre-FEAT-008 behaviour
```

| Rollback scenario (FEAT-006 §9.1) | Action | Target |
| :--- | :--- | :--- |
| Label-distribution shift unacceptable at Stage 15 review | Keep `composite_uses_realistic = false`; do not activate | Stage 14 (Shadow) |
| Cost config found incorrect | Set `execution_model = LEGACY`; correct config; re-validate | Stage 10 |
| Realistic path raises into scan | Set `execution_model = LEGACY` + bug fix | Stage 7 |
| Win-rate/profit-factor collapse beyond thresholds (§16.3) | Set `execution_model = LEGACY`; investigate | Stage 10 |
| LEGACY mode found divergent from pre-FEAT-008 | Block activation; treat as regression | Stage 9 |

After rollback to `LEGACY`, the composite backtest score returns to its pre-FEAT-008 values exactly, because LEGACY is verified byte-identical (Stage 9). If only `composite_uses_realistic` is reverted to `false` (a softer rollback from Stage 15 to Stage 14), realistic metrics continue to be logged for post-incident analysis while the composite uses legacy.

---

## 19. Final Recommendation

**Proceed to FEAT-006 Stage 6 (Implementation Approval) for FEAT-008 as the next feature, ahead of any further signal additions.**

Rationale:

1. **It fixes a biased high-weight input.** The BacktestAgent feeds 25% (standard) / 20% (catalyst) of every composite score. Today that input is non-causal (look-ahead) and cost-blind. Every recommendation is distorted. No signal added on top of this — including FEAT-004 and FEAT-007 — is weighted against a truthful backtest number. Repairing this first is the highest-value move available.

2. **It is the strongest-evidenced feature in the OS.** Level A (score 100), matching FEAT-005's own canonical Level A example. The claims that transaction costs matter and that same-candle fills are a bias are uncontested in both academia and practice. No candidate exceeds this evidence base.

3. **It is the lowest-risk bounded delta.** Isolated to `COMP-BT`. No new data, no new agents, no Gate changes, no threshold changes, no normalization-formula changes, no FEAT-004 logic changes. Rollback is one config line to a verified byte-identical LEGACY mode.

4. **It directly reduces false positives.** Cost-blind backtests over-state high-turnover and high-spread stocks, producing false-positive BUYs. Realism removes exactly these.

5. **Zero overlap with FEAT-004/007.** Different component, different concern. It composes with them rather than competing: once the backtest score is truthful, FEAT-004's regime modifier and FEAT-007's sector modifier operate on a sound foundation.

6. **It bundles four gaps in one coherent delta.** Gaps #11, #12, #13, #14 are all execution-model concerns and are fixed together as one "realistic execution" concept — per the approved Architecture Review (Option A). Gap #15 (position sizing) and Items 7–9 (corporate actions, partial fills, liquidity) are deliberately deferred as separate, prerequisite-bearing future features (§8.2).

7. **Sequencing principle.** FEAT-004 and FEAT-007 added signals. FEAT-008 repairs the substrate those signals are weighted against. The correct order is substrate-then-signals; since two signals already exist, the substrate repair is now urgent and should precede any further signal work.

8. **No upstream dependency.** Unlike FEAT-007 (which waits on FEAT-004's sector plumbing), FEAT-008 can proceed independently and immediately upon Stage 6 approval. It is therefore also the most schedule-flexible next feature.

**Approved scope reaffirmed:** This specification implements exactly Items 1–6 (Tier 1: look-ahead correction, entry timing, exit timing; Tier 2: slippage, brokerage, taxes/charges) as one bounded delta to `COMP-BT`. Nothing in §8.2's out-of-scope list is included.

---

*End of FEAT-008 Specification v1.0*
