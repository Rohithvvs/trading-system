# Governance Consistency Review
**Document:** GOVERNANCE_CONSISTENCY_REVIEW.md
**Version:** 1.0
**Date:** 2026-07-12
**Author:** Principal Software Architect & Governance Reviewer
**Status:** Review — concludes with a single recommendation for the System Owner.
**Scope:** Governance consistency between FEAT-007, ADR-003, and dependent planning documents only.
**Constraints honored:** FEAT-007 not modified. ADR-003 not modified. No code generated. No feature redesigned. This is a review and recommendation only.

---

## 1. Current Situation

A governance conflict exists between two authoritative documents:

| Document | Formula specified | Status | Date |
| :--- | :--- | :--- | :--- |
| **FEAT-007 specification** (v1.0) | **Ratio**: `sector_roc20 / benchmark_roc20` with thresholds 1.10 / 0.90 | Complete, "Ready for architecture review (FEAT-006 Stage 5)" | 2026-07-11 |
| **ADR-003** (Accepted) | **Difference**: `sector_roc20 - bm_roc20` (Option C-Revised) | **Accepted** | 2026-07-11 |

Both documents were authored on the same date. ADR-003 was created specifically to resolve the formula conflict that the FEAT-007 spec created (ADR-003 Section 1: *"This ADR decides the canonical formula and which implementation survives"*). ADR-003's evidence report (10,827 real NSE observations) conclusively rejected the ratio formula on every fair test:

| Test | Result | Threshold | Verdict |
| :--- | :--- | :--- | :--- |
| Binary disagreement (spec thresholds) | 40.3% | >20% | Exceeds |
| Quantile-matched disagreement (threshold-free) | 27.2% | >20% | Exceeds |
| Spearman rank correlation | 0.188 | closer to 1 = agreement | Near-independent |

ADR-003 Section 0 explicitly states the consequence:

> *"The FEAT-007 specification must be revised to document the difference formula in place of the ratio formula it currently specifies."*

> *"This revision is the responsibility of the FEAT-007 specification owner; ADR-003 does not modify FEAT-007 directly."*

**The conflict is not ambiguous.** ADR-003 mandates a revision of FEAT-007. The revision has not been performed. Two authoritative documents currently describe different implementations of the same concept.

---

## 2. Relationship Review

### 2.1 Document hierarchy and authority

The repository contains a layered governance structure. Authority flows top-down:

```
  +----------------------------------------------------------+
  |  LAYER 1 — ARCHITECTURE DECISION RECORDS (ADRs)         |
  |  ADR-001, ADR-002, ADR-003 (all Accepted)               |
  |  Authority: HIGHEST — resolve architectural conflicts.  |
  |             Explicitly supersede specs on the decided    |
  |             point.                                       |
  +----------------------------------------------------------+
                            |
                            v
  +----------------------------------------------------------+
  |  LAYER 2 — GOVERNANCE FRAMEWORK (FEAT-001..006)          |
  |  Shared Context Pack, Taxonomy, Rulebook, Evidence       |
  |  Hierarchy, Research Lifecycle                           |
  |  Authority: HIGH — define the rules all features follow. |
  |             Frozen/complete.                              |
  +----------------------------------------------------------+
                            |
                            v
  +----------------------------------------------------------+
  |  LAYER 3 — FEATURE SPECIFICATIONS (FEAT-004, 007, 008)   |
  |  Feature-level design within the governance framework.   |
  |  Authority: MEDIUM — authoritative for their feature     |
  |             UNLESS an ADR decides otherwise on a          |
  |             specific point.                               |
  +----------------------------------------------------------+
                            |
                            v
  +----------------------------------------------------------+
  |  LAYER 4 — PLANNING DOCUMENTS                            |
  |  Implementation Planning Review, Implementation Master   |
  |  Plan, FEAT-004 Implementation Breakdown                 |
  |  Authority: LOW — plans are subordinate to specs and     |
  |             ADRs. They describe HOW to implement, not     |
  |             WHAT to build.                                |
  +----------------------------------------------------------+
                            |
                            v
  +----------------------------------------------------------+
  |  LAYER 5 — AUDIT / OPERATIONAL DOCUMENTS                 |
  |  Phase-0 Repository Readiness Report, Git Baseline Plan  |
  |  Authority: LOWEST — audits and plans-about-plans.       |
  |             They report the state of the repository and   |
  |             recommend actions; they do not decide         |
  |             architecture or feature design.               |
  +----------------------------------------------------------+
```

**The key principle:** An accepted ADR supersedes any feature specification on the specific point it decides. This is the standard ADR governance model and is reinforced by ADR-003's own language (*"This ADR decides the canonical formula"*).

### 2.2 Per-document analysis

#### ADR-003 (Layer 1 — Accepted)
- **Status:** Accepted (2026-07-11), Option C-Revised.
- **Decision:** The difference formula is canonical. The ratio formula is rejected on evidence.
- **Mandated action:** FEAT-007 specification must be revised.
- **Scope of authority:** The formula only. ADR-003 Section 0 explicitly states that any mechanic upgrade (three-state, score deltas, pre-Gate placement) is a *"separate, evidence-backed step"* — not part of this ADR's decision.
- **Self-consistency:** Fully self-consistent. The ADR was originally Proposed with a recommendation for Option D (ratio), but the evidence report resolved the condition against Option D. The decision record (Sections 7, 11, 11.1) documents this change transparently.

#### FEAT-007 specification (Layer 3 — v1.0)
- **Status:** v1.0, "Ready for architecture review (FEAT-006 Stage 5)."
- **Formula specified:** Ratio (`sector_roc20 / benchmark_roc20`) throughout:
  - Section 9.1: defines `relative_strength_ratio` as the ratio.
  - Section 9.2: classifies STRONG/NEUTRAL/WEAK on ratio thresholds (1.10 / 0.90).
  - Section 10: declares zero new data dependencies (consumes FEAT-004's `compute_sector_strength` outputs).
  - Section 11.2: logs `sector_relative_strength_ratio`.
  - Section 17: states FEAT-007 "reuses FEAT-004's `SectorStrengthHelper`, sector mapping, benchmark OHLCV, and `relative_strength_ratio` computation without modification."
- **Conflict with ADR-003:** Direct and complete. Every formula reference in FEAT-007 contradicts ADR-003's accepted decision.
- **Dependency on FEAT-004:** FEAT-007 Section 10 and Section 17 state that FEAT-007 consumes `compute_sector_strength`'s outputs. `compute_sector_strength` (FEAT-004 Implementation Breakdown Section 2.5, code at `feat004_regime_overlay.py:381`) uses the ratio formula. ADR-003 Section 8.5 mandates removing this duplicate. So FEAT-007's stated dependency on `compute_sector_strength` is also affected.

#### Implementation Planning Review (Layer 4)
- **Status:** v1.0, "Planning review. No production code."
- **Conflict points:**
  - Section 1.2: states FEAT-007 has a **hard code dependency** on FEAT-004's `compute_sector_strength` and its outputs (`sector_roc20`, `benchmark_roc20`, `relative_strength_ratio`, `sector_regime_state`).
  - Section 3.2: lists `compute_sector_strength` as producing "the exact inputs FEAT-007 consumes."
  - Section 5 dependency graph: shows "FEAT-007 consumes `compute_sector_strength` (Section 2.5), sector mapping, sector OHLCV cache, `benchmark_roc20`."
  - Section 6: recommends FEAT-004's `compute_sector_strength` be "implemented but kept at v1 explanation-only behavior" and FEAT-007 "attaches the score effect as its own delta."
  - Section 7 Phase 3: "Implement one overlay function consuming `compute_sector_strength`."
- **Impact of ADR-003:** The dependency described here is on a helper that uses the rejected ratio formula. If `compute_sector_strength` is removed (per ADR-003 Section 8.5) or revised to the difference formula, the dependency chain described in this document is broken. The Planning Review does not mention ADR-003 or the formula conflict — it was written before ADR-003 was accepted (or contemporaneously, without incorporating the ADR's outcome).

#### Phase-0 Repository Readiness Report (Layer 5)
- **Status:** v1.0, implementation gate.
- **Treatment of the conflict:** Correctly identifies it as **blocker B2 (Critical)**: *"ADR-003 mandates FEAT-007 spec revision (ratio -> difference) but constraint forbids modifying FEAT docs."*
- **Self-consistency:** Fully consistent. The report identifies the conflict, marks it Critical, and includes it in the NO-GO decision. No conflict with ADR-003.

#### Git Baseline Plan (Layer 5)
- **Status:** v1.0, plan.
- **Treatment of the conflict:** Notes in Section 11 that the Git baseline resolves blocker B1 (uncommitted feature layer) but *"does NOT remove blockers B2 (ADR-003 vs FEAT-007 spec conflict) or B3 (ADR acceptance status reconciliation). Those remain System Owner decisions."*
- **Self-consistency:** Fully consistent. The plan correctly defers the governance conflict to the System Owner.

### 2.3 Cascading conflict map

The formula conflict is not isolated to FEAT-007. It cascades through multiple documents:

| Document | Section | What it says | Conflict with ADR-003 |
| :--- | :--- | :--- | :--- |
| **FEAT-007 spec** | Section 9.1, 9.2 | Ratio formula + 1.10/0.90 thresholds | **Direct** — formula rejected |
| **FEAT-007 spec** | Section 10 | Consumes `compute_sector_strength` outputs | **Indirect** — compute_sector_strength uses ratio |
| **FEAT-007 spec** | Section 17 | "reuses... `relative_strength_ratio` computation without modification" | **Direct** — ratio rejected |
| **FEAT-004 spec** | Section 6 | Sector-strength extension uses ratio formula | **Indirect** — FEAT-004's sector helper uses rejected formula |
| **FEAT-004 Implementation Breakdown** | Section 2.5 | `compute_sector_strength` computes `relative_strength_ratio = round(sector_roc20 / bm_roc, 4)` | **Direct** — code helper uses rejected formula |
| **Implementation Planning Review** | Section 1.2, 3.2, 5, 6, 7 | FEAT-007 hard-depends on `compute_sector_strength`'s ratio outputs | **Indirect** — dependency on rejected formula path |
| **Implementation Master Plan** | R3, Section 3, 5 | Flags two-formula conflict; says "Decide formula (Phase 3)" | **Resolved** — ADR-003 decided; master plan's "decide later" is now stale |

**Summary:** The ratio formula appears in 4 governance/planning documents and 1 code module. ADR-003's decision affects all of them. However, ADR-003's mandate is specifically about FEAT-007. The other documents are affected by cascade, not by direct mandate.

---

## 3. Authoritative Document Determination

### 3.1 Which document is authoritative on the formula question?

**ADR-003 is authoritative.**

Rationale:
1. **ADR governance model.** An accepted ADR is the highest-authority architectural decision. It exists specifically to resolve conflicts that specifications cannot resolve themselves. ADR-003 Section 1 states its purpose: *"This ADR decides the canonical formula and which implementation survives."*
2. **Recency and evidence.** ADR-003 was accepted based on a completed evidence report (10,827 observations) that rejected the ratio formula. The FEAT-007 spec was written before that evidence existed (or contemporaneously, without incorporating it). The ADR represents the more informed position.
3. **ADR-003's own statement of consequence.** Section 0: *"The FEAT-007 specification must be revised to document the difference formula in place of the ratio formula it currently specifies."* This is an explicit mandate, not a suggestion.
4. **ADR-003's scope discipline.** The ADR decides only the formula. It explicitly defers mechanic upgrades (three-state, score deltas, pre-Gate placement) to a separate step. This means FEAT-007's score-delta mechanic, STRONG cap, REJECT immutability, and downgrade threshold are NOT affected by ADR-003 — only the formula and its thresholds are.

### 3.2 Which document is authoritative on the mechanic question (score deltas, states, placement)?

**FEAT-007 specification remains authoritative on the mechanic**, subject to the formula revision.

ADR-003 Section 0: *"any mechanic upgrade (three-state, score deltas, pre-Gate placement) is a separate, evidence-backed step under the IMPLEMENTATION_MASTER_PLAN, not a formula change."*

This means:
- The score deltas (+1.5 STRONG, -3.0 WEAK, 0.0 NEUTRAL/UNKNOWN) remain FEAT-007's design.
- The STRONG cap, REJECT immutability, and 74.0 downgrade threshold remain FEAT-007's design.
- The pre-Gate placement (composite -> FEAT-004 -> FEAT-007 -> Strict Buy Gate) remains FEAT-007's design.
- **Only the formula and its thresholds change** from ratio to difference.

### 3.3 Which document is authoritative on the implementation sequencing?

**Implementation Planning Review remains authoritative on sequencing** (FEAT-008 -> FEAT-004 -> FEAT-007), but its description of FEAT-007's dependency on `compute_sector_strength` must be updated to reflect ADR-003's formula decision.

---

## 4. Must FEAT-007 Be Revised?

**Yes. This is not optional.**

ADR-003 Section 0 explicitly mandates:

> *"The FEAT-007 specification must be revised to document the difference formula in place of the ratio formula it currently specifies."*

> *"This revision is the responsibility of the FEAT-007 specification owner; ADR-003 does not modify FEAT-007 directly."*

The ADR deliberately does not modify FEAT-007 directly — it defers the revision to the specification owner, respecting the separation between architectural decisions (ADRs) and feature specifications (FEAT docs). But the mandate is unambiguous: the revision must happen.

**Consequence of not revising:** If FEAT-007 is implemented as currently written (ratio formula), the implementation would directly contradict an accepted ADR. This would:
1. Violate the ADR governance model (accepted ADRs are binding).
2. Introduce the proven-numerically-unstable ratio formula (40.3% disagreement, sign-flips in 93% of down-market observations).
3. Create a code-vs-ADR conflict that would surface during audit, shadow validation, or production incident review.
4. Make the repository's governance internally contradictory — an audit gate (Phase-0 Report) would permanently block implementation.

---

## 5. Revision Type

### 5.1 Options considered

| Option | Description | Fit |
| :--- | :--- | :--- |
| **Minor update / patch** (v1.0 -> v1.0.1) | Typo fixes, clarification, no substantive change | **No** — the formula is the core computation, not a typo |
| **New revision** (v1.0 -> v1.1) | Substantive change directed by an accepted ADR; feature concept unchanged | **Yes** — the formula changes but the feature's purpose, component tag, situation tag, evidence level, score-delta mechanic, and placement all remain |
| **Major revision** (v1.0 -> v2.0) | Fundamental redesign of the feature | **No** — ADR-003 explicitly scopes the change to the formula only; the mechanic is unaffected |
| **Superseding document** (FEAT-007a) | Replace FEAT-007 entirely with a new document | **No** — the feature is the same (sector RS overlay); only the formula changes |

### 5.2 Recommendation: **New revision (v1.0 -> v1.1)**

**Rationale:**
1. The feature concept is unchanged: FEAT-007 v1.1 is still a sector-relative-strength overlay in `COMP-REC` with `SIT-SR` primary tag, Level B evidence, soft score modifier with STRONG/WEAK/NEUTRAL/UNKNOWN states, pre-Gate placement.
2. The change is substantive (core formula) but bounded (formula + thresholds only, per ADR-003's scope discipline).
3. The change is directed by an accepted ADR — it is not a redesign but a conformance update.
4. A revision (not a patch) preserves the audit trail: v1.0 shows the original design; v1.1 shows the ADR-directed correction. Reviewers can diff the two and see exactly what ADR-003 changed.
5. A superseding document would fragment the governance trail and break references in the Implementation Planning Review, Phase-0 Report, and Git Baseline Plan.

### 5.3 Scope of the v1.1 revision

**What changes in v1.1 (per ADR-003 mandate):**
| Section | v1.0 (current) | v1.1 (revised) |
| :--- | :--- | :--- |
| Section 9.1 | `relative_strength_ratio = sector_roc20 / benchmark_roc20` | `sector_rs_value = sector_roc20 - benchmark_roc20` (difference formula) |
| Section 9.2 | STRONG > 1.10, NEUTRAL 0.90-1.10, WEAK < 0.90 | Thresholds on the difference scale (to be calibrated; ADR-003 retains SR-003's binary WEAK/STRENGTH as starting point) |
| Section 10 | "consumes FEAT-004's `compute_sector_strength` outputs" | Updated dependency: consumes the difference-formula path (SR-003 reference or a revised helper), not the ratio-formula `compute_sector_strength` |
| Section 11.2 | Logs `sector_relative_strength_ratio` | Logs `sector_rs_value` (difference) instead of ratio |
| Section 17 | "reuses... `relative_strength_ratio` computation" | "reuses... the difference-formula sector RS computation" |
| Header | v1.0 | v1.1, with a revision note referencing ADR-003 |

**What does NOT change in v1.1 (per ADR-003 scope discipline):**
- Component tag (`COMP-REC`), situation tag (`SIT-SR`), evidence level (Level B).
- Score deltas (+1.5 STRONG, -3.0 WEAK, 0.0 NEUTRAL/UNKNOWN).
- STRONG cap, REJECT immutability, 74.0 downgrade threshold.
- Pre-Gate placement (composite -> FEAT-004 -> FEAT-007 -> Strict Buy Gate).
- Safe-fallback behavior (UNKNOWN on any failure).
- Logging schema shape (FEAT-007 Section 11.2 mirrors FEAT-004 Section 8).
- Unit test plan structure (14 tests + cross-feature abstention test).

### 5.4 Open question for the System Owner: thresholds on the difference scale

ADR-003 retains SR-003's binary WEAK/STRENGTH classification as the starting point. FEAT-007 v1.0 has a three-state STRONG/NEUTRAL/WEAK classification. ADR-003 Section 0 says mechanic upgrades (including three-state) are a "separate, evidence-backed step." The v1.1 revision must therefore decide:
- **Option (a):** Keep three-state (STRONG/NEUTRAL/WEAK) but on the difference scale. New thresholds must be proposed (e.g., STRONG > +X pp, NEUTRAL -X to +X pp, WEAK < -X pp). This is a mechanic upgrade on top of the formula change.
- **Option (b):** Collapse to binary (WEAK/STRENGTH) matching SR-003, defer three-state to a future evidence-backed step. Score deltas become: WEAK -3.0, STRENGTH +1.5, no NEUTRAL.

This is a specification decision, not an ADR decision. The System Owner (as FEAT-007 specification owner) must choose. The review recommends **Option (b)** for v1.1 (minimal change, formula conformance only, defer three-state to a later revision) to keep the revision scope tightly bounded by ADR-003.

---

## 6. Safest Governance Approach

### 6.1 Principle: minimal-blast-radius revision

The safest approach is the one that:
1. Satisfies ADR-003's mandate (formula revision).
2. Changes the fewest documents.
3. Preserves the audit trail (v1.0 retained, v1.1 created).
4. Does not cascade into code changes (governance only).
5. Does not require revisiting ADR-001 or ADR-002.

### 6.2 Recommended approach

| Step | Action | Documents touched | Rationale |
| :--- | :--- | :--- | :--- |
| 1 | Revise FEAT-007 to v1.1 (formula + thresholds + dependency reference) | `FEAT-007_SECTOR_RELATIVE_STRENGTH.md` only | Satisfies ADR-003 mandate |
| 2 | Add a revision note at the top of FEAT-007 v1.1 citing ADR-003 | Same file | Preserves audit trail |
| 3 | Do NOT revise FEAT-004 spec or Implementation Breakdown now | — | FEAT-004's `compute_sector_strength` is dead code (ADR-002); its formula is wrong but inert. Fix it during Phase-2 implementation, not during governance. |
| 4 | Add an addendum note to the Implementation Planning Review | `IMPLEMENTATION_PLANNING_REVIEW.md` | One-line note: "FEAT-007's dependency on `compute_sector_strength` is superseded by ADR-003; FEAT-007 v1.1 consumes the difference-formula path." |
| 5 | Do NOT revise ADR-003 | — | ADR-003 is accepted and self-consistent |
| 6 | Do NOT revise the Phase-0 Report or Git Baseline Plan | — | They correctly identify the conflict; resolving it makes them accurate, not stale |

### 6.3 What explicitly should NOT happen

- **Do NOT create a new ADR** to resolve the conflict. ADR-003 already resolves it. A new ADR would add governance overhead without new information.
- **Do NOT supersede FEAT-007** with a new document. The feature is the same; only the formula changes.
- **Do NOT revise FEAT-004's spec or implementation breakdown** as part of this governance update. FEAT-004's `compute_sector_strength` is dead code (never wired, per ADR-002). Its ratio formula is wrong but inert. The formula correction for FEAT-004's helper is a Phase-2 implementation concern (when the helper is either revised to the difference formula or removed per ADR-003 Section 8.5), not a governance prerequisite.
- **Do NOT attempt to make the ratio and difference formulas coexist.** ADR-003 Section 11 Option E (keep both, segmented) is explicitly discouraged: *"two formulas for one concept is the core problem this ADR exists to solve."*

---

## 7. Migration Strategy for Governance Documents

### 7.1 Documents that must change

| Document | Change type | Scope | Owner |
| :--- | :--- | :--- | :--- |
| `FEAT-007_SECTOR_RELATIVE_STRENGTH.md` | **Revision** (v1.0 -> v1.1) | Formula (Section 9.1, 9.2), dependency (Section 10, 17), log field (Section 11.2), header + revision note | FEAT-007 specification owner (System Owner) |
| `IMPLEMENTATION_PLANNING_REVIEW.md` | **Addendum** | One note in Section 1.2 and Section 3.2: FEAT-007's dependency on `compute_sector_strength` is superseded by ADR-003 | Plan author |

### 7.2 Documents that must NOT change

| Document | Reason |
| :--- | :--- |
| `ADR-003_sector_relative_strength_formula.md` | Accepted, self-consistent, authoritative. Modifying an accepted ADR violates governance. |
| `ADR-001_backtest_execution_model.md` | Accepted, unrelated to the formula conflict. |
| `ADR-002_market_regime_consolidation.md` | Accepted, unrelated to the formula conflict (though it notes the ratio formula in FEAT-004's helper). |
| `EVIDENCE_REPORT_SR_formula_comparison.md` | Evidence report; its data and conclusions are final. |
| `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md` | FEAT-004's sector-strength extension (Section 6) uses the ratio formula, but it is v1 explanation-only metadata and FEAT-004 is dead code. Correcting FEAT-004's helper is a Phase-2 implementation concern. |
| `FEAT-004_IMPLEMENTATION_BREAKDOWN.md` | Same reasoning — `compute_sector_strength` is a dead helper. Correct during Phase-2. |
| `FEAT-001..006 governance docs` | Frozen/complete, unaffected. |
| `FEAT-008_REALISTIC_TRADE_EXECUTION_MODEL.md` | Unrelated to the formula conflict. |
| `PHASE0_REPOSITORY_READINESS_REPORT.md` | Correctly identifies the conflict. After resolution, it becomes accurate (blocker B2 lifted). No change needed. |
| `GIT_BASELINE_PLAN.md` | Correctly defers the conflict. No change needed. |
| `IMPLEMENTATION_MASTER_PLAN.md` | Its R3 flag ("Decide formula — Phase 3") is now resolved by ADR-003. An addendum note is optional but not required since ADR-003 is the authoritative resolution. |

### 7.3 Revision procedure for FEAT-007 v1.1

The specification owner should:

1. **Read ADR-003 Section 0** for the exact mandate and scope boundary.
2. **Update the header**: version v1.0 -> v1.1; status "Ready for implementation (revised per ADR-003)."
3. **Add a revision note** immediately after the header:
   > *"v1.1 revises the sector-relative-strength formula from the ratio (`sector_roc20 / benchmark_roc20`) to the difference (`sector_roc20 - benchmark_roc20`) per ADR-003 (Accepted, Option C-Revised). The ratio formula was rejected on evidence (40.3% binary disagreement, Spearman rho = 0.188 across 10,827 observations). The score-delta mechanic, STRONG cap, REJECT immutability, pre-Gate placement, and evidence level are unchanged. See ADR-003 for the full decision record."*
4. **Replace the formula** in Section 9.1: ratio -> difference.
5. **Update the classification thresholds** in Section 9.2: from ratio thresholds (1.10/0.90) to difference-scale thresholds (per System Owner decision — see Section 5.4 of this review).
6. **Update Section 10** (inputs): replace the dependency on `compute_sector_strength`'s ratio outputs with the difference-formula path (SR-003 reference or a revised helper).
7. **Update Section 11.2** (log payload): replace `sector_relative_strength_ratio` with `sector_rs_value` (difference).
8. **Update Section 17** (final recommendation): replace "reuses... `relative_strength_ratio` computation" with "reuses... the difference-formula sector RS computation (per ADR-003)."
9. **Update the worked examples** in Section 9.5 to use the difference formula.
10. **Update the unit test plan** (Section 15.2) inputs to use difference-scale values.
11. **Retain v1.0** in git history (do not delete or overwrite the original; the revision is a new version).

### 7.4 Addendum procedure for Implementation Planning Review

Add a note to Section 1.2 (direct dependencies table, FEAT-007 row):
> *"Addendum 2026-07-12: FEAT-007's dependency on `compute_sector_strength`'s ratio-formula outputs is superseded by ADR-003 (Accepted, Option C-Revised). FEAT-007 v1.1 consumes the difference-formula path. The hard dependency on FEAT-004's sector plumbing (sector mapping, sector OHLCV cache, benchmark OHLCV) remains."*

This preserves the original Planning Review as a historical record while noting the ADR-003 correction.

---

## 8. Before or After the Git Baseline Commit

### 8.1 Recommendation: **BEFORE the Git baseline commit.**

### 8.2 Rationale

| Factor | Before baseline | After baseline |
| :--- | :--- | :--- |
| **Baseline integrity** | The tagged baseline is internally consistent — no known-critical governance conflict at the implementation gate | The tagged baseline contains a known-critical conflict (blocker B2) |
| **Rollback safety** | `git reset --hard phase-0-baseline` restores a consistent state | Rollback restores a conflicting state; a future implementer could unknowingly implement the ratio formula from the baseline spec |
| **Phase-0 Report blocker B2** | Resolved before baseline — the baseline truly gates Phase-1 | Blocker B2 persists past the baseline; the "implementation gate" does not actually gate |
| **Git bisect utility** | Baseline is a clean reference point | Baseline contains a known defect; bisect across it is confusing |
| **Audit trail** | v1.0 -> v1.1 revision is visible in the commit history before the tag | v1.0 is tagged, then v1.1 comes after — the tag captures the wrong version |
| **Effort** | One governance-doc revision + one addendum before commit #2 | Same work, but now it's a post-baseline commit that requires re-tagging or living with a broken tag |
| **Risk** | Low — governance docs only, no code | Higher — if Phase-1 starts against the baseline before the revision lands, implementers code against the wrong formula |

### 8.3 Integration with the Git Baseline Plan

The Git Baseline Plan (Section 5) defines 6 commits. The FEAT-007 v1.1 revision should be performed **before commit #2** (governance docs) so that commit #2 captures the revised spec, not the conflicting one.

**Revised commit sequence:**

| # | Commit | Includes FEAT-007 v1.1? |
| :--- | :--- | :--- |
| 1 | Chore: untrack logs + gitignore scratch | No |
| **pre-2** | **Governance: revise FEAT-007 to v1.1 per ADR-003 + addendum to Planning Review** | **Yes — this is the revision step** |
| 2 | Governance: add FEAT-001..008 governance & spec documents | Yes — commit #2 now captures v1.1 |
| 3 | Architecture: add ADR-001/002/003 + evidence | No |
| 4-6 | Backend, frontend, tag | No |

The "pre-2" step is not a separate commit — it is a file edit performed before staging commit #2. The edit produces FEAT-007 v1.1 on disk, which is then staged as part of commit #2's governance-doc batch.

### 8.4 What if the System Owner cannot perform the revision immediately?

If the FEAT-007 v1.1 revision cannot be performed before the baseline (e.g., the specification owner is unavailable), the **next safest option** is:

1. Proceed with the Git baseline as planned (committing FEAT-007 v1.0).
2. Tag it `phase-0-baseline-pending-feat007-revision` (not `phase-0-baseline`).
3. Perform the v1.1 revision as the first commit after the baseline.
4. Re-tag as `phase-0-baseline` on the post-revision commit.
5. Delete the interim tag.

This preserves a clean tag on the consistent state while allowing the mechanical git work to proceed. However, it is strictly inferior to doing the revision first, because it creates an interim tagged state that is known-broken.

---

## 9. Final Recommendation

### **The System Owner should revise FEAT-007 to v1.1 BEFORE the Git baseline commit.**

**Single recommendation:** Revise `FEAT-007_SECTOR_RELATIVE_STRENGTH.md` from v1.0 to v1.1, replacing the ratio formula with the difference formula per ADR-003 (Accepted, Option C-Revised), then proceed with the Git Baseline Plan so that the `phase-0-baseline` tag captures a governance-consistent repository.

**Specifically:**
1. **Formula:** Replace `sector_roc20 / benchmark_roc20` (ratio) with `sector_roc20 - benchmark_roc20` (difference) throughout FEAT-007.
2. **Thresholds:** Adopt binary WEAK/STRENGTH on the difference scale for v1.1 (matching SR-003 as ADR-003's reference implementation). Defer three-state classification to a future evidence-backed revision.
3. **Dependency:** Update FEAT-007 Section 10 and Section 17 to reference the difference-formula path (SR-003) instead of `compute_sector_strength`'s ratio outputs.
4. **Scope:** Do NOT change the score deltas, STRONG cap, REJECT immutability, pre-Gate placement, evidence level, or component/situation tags — ADR-003 scopes the change to the formula only.
5. **Addendum:** Add a one-line note to the Implementation Planning Review (Section 1.2) noting ADR-003 supersedes the `compute_sector_strength` dependency.
6. **Timing:** Perform the revision before Git Baseline Plan commit #2, so the `phase-0-baseline` tag is internally consistent.
7. **Do NOT** modify ADR-003, ADR-001, ADR-002, the evidence report, FEAT-004 spec, FEAT-004 Implementation Breakdown, FEAT-001..006 governance docs, FEAT-008 spec, the Phase-0 Report, or the Git Baseline Plan.

**This resolves Phase-0 Repository Readiness Report blocker B2 (Critical) and is a prerequisite for the NO-GO -> GO transition for Phase-1.**

---

*End of GOVERNANCE_CONSISTENCY_REVIEW v1.0*
