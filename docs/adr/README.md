# Architecture Decision Records

These three ADRs resolve the architecture blockers identified in the
`IMPLEMENTATION_MASTER_PLAN` codebase audit (2026-07-11). Each is **proposed,
not final** — they become authoritative only on System Owner sign-off.

| ADR | Decides | Blocks | Recommended option |
| :--- | :--- | :--- | :--- |
| [ADR-001](ADR-001_backtest_execution_model.md) | Backtest execution model — reconcile the existing two-pass realism engine with the FEAT-008 spec | Phase 1 | **Option B** — brand, switch, verify (default REALISTIC) |
| [ADR-002](ADR-002_market_regime_consolidation.md) | Market regime — reconcile live SR-004 with dead-code FEAT-004 module and the FEAT-004 spec | Phase 2 | **Option C** — merge with separated responsibilities |
| [ADR-003](ADR-003_sector_relative_strength_formula.md) | Sector RS formula — reconcile live SR-003 (difference) with the FEAT-007 spec (ratio) | Phase 3 | **Option D** — adopt ratio (conditional on disagreement-rate measurement) |

## Status legend
- **Proposed** — written, not yet accepted; open for the System Owner decision named in each ADR.
- **Accepted** — decided; the IMPLEMENTATION_MASTER_PLAN phases may proceed on the chosen option.
- **Superseded** — replaced by a later ADR.

## Dependencies between ADRs
- ADR-001 is independent and **gates Phase 1**. It must be decided first.
- ADR-002 gates Phase 2. It is independent of ADR-001 but its shadow validation
  should run against the ADR-001-resolved composite.
- ADR-003 gates Phase 3. It is *conditioned on a Phase-0 measurement*
  (disagreement-rate table, master-plan task 0.3) and must not be finalised
  without that data.

## What these ADRs do NOT do
- Write or change production code.
- Modify FEAT-001 through FEAT-008 specifications.
- Pre-empt the System Owner's decision authority — each ADR recommends an option
  but states it is not assumed accepted.
