# RESEARCH_IDEA_LIFECYCLE — Research Idea Lifecycle Framework
**Version:** 1.0 — FEAT-006 Baseline
**Date:** 2026-07-11
**Scope:** This document defines the canonical, deterministic workflow that every future trading recommendation enhancement follows from idea submission until production monitoring and rollback. It governs **process sequencing only**. It does not redefine evidence quality (FEAT-005), component taxonomy (FEAT-002), classification rules (FEAT-003), trading strategy, runtime architecture, or production code.

---

## 1. Purpose

The Research Operating System already defines *what* an idea modifies (`COMP-*`, FEAT-002), *where* it applies (`SIT-*`, FEAT-002), *how* it is submitted (FEAT-003 §5), and *how well-proven* it is (Levels A–E, FEAT-005). It does not yet fix the **order** in which these gates must be passed, nor the path an idea takes from a written proposal to a monitored production feature.

FEAT-006 closes that gap. It defines one canonical, deterministic lifecycle — seventeen stages — that every future idea must traverse. No stage may be skipped. No stage may be reordered. No idea may reach production without passing every preceding stage in sequence.

This document governs **process sequencing only**. It explicitly does **not** redefine:

- Evidence quality or the five evidence levels — owned by **FEAT-005**
- Component or situation taxonomy — owned by **FEAT-002**
- Classification rules and the submission template — owned by **FEAT-003**
- Trading strategy, weights, thresholds, or the pipeline — owned by **FEAT-001**
- Runtime architecture, agents, or production code — owned by the codebase

FEAT-006 sequences existing governance into a single spine. It introduces no new evaluation criteria of its own.

---

## 2. Position Within the Research Operating System

FEAT-006 is a **governance document**, sibling to FEAT-001, FEAT-002, FEAT-003, and FEAT-005. It is **not** a feature specification like FEAT-004. It introduces no runtime behavior, no production code, no new agents, and no new runtime components.

### 2.1 Dependency map

```
FEAT-001  Shared Context Pack          (truth: architecture, constraints, gaps)
   │
FEAT-002  Component × Situation        (vocabulary: COMP-*, SIT-*)
   │
FEAT-003  Classification Rulebook      (validation rules + submission template)
   │
FEAT-005  Evidence Hierarchy           (evidence strength: Levels A–E)
   │
FEAT-006  Research Idea Lifecycle      ← THIS DOCUMENT (canonical stage spine)
   │
FEAT-004  Market Regime Overlay        (first FEATURE — an instance of this lifecycle)
   │
Future features                        (each traverses the FEAT-006 spine)
```

FEAT-006 sits **above** FEAT-005 and **consumes** it as one stage (Stage 4). It generalizes the shadow→active→rollback precedent that FEAT-004 established into a reusable lifecycle. It does not modify any document above or below it.

### 2.2 Integration with each existing document

| Document | Relationship | What FEAT-006 consumes from it | What FEAT-006 changes about it |
| :--- | :--- | :--- | :--- |
| **FEAT-001** | Consumes | §2 constraints (determinism, brownfield safety, human-in-the-loop, no live LLM); §8 known gaps (referenced by number); §10 eight evaluation axes (consumed at Stage 3); §11 output rules (consumed at Stage 1–2) | **Nothing.** |
| **FEAT-002** | Consumes | The closed `COMP-*` and `SIT-*` vocabularies (consumed at Stage 2) | **Nothing.** No new tags. |
| **FEAT-003** | Consumes | The §5 Candidate Idea Submission Template (consumed at Stage 1); the four hard rules and eight instructions (consumed at Stages 2 and 5) | **Nothing.** |
| **FEAT-004** | Uses as worked example | FEAT-004's shadow→active→rollback becomes a specialization of Stages 14–17 | **Nothing.** FEAT-004 is retrospectively readable as the first instance of this lifecycle. |
| **FEAT-005** | Consumes | The five evidence levels A–E and the scoring rubric (consumed at Stage 4); the promotion workflow and re-evaluation triggers (consumed at Stages 4, 10, 16) | **Nothing.** Evidence levels are owned entirely by FEAT-005. |

### 2.3 What FEAT-006 does NOT own

To preserve single responsibility across the OS:

- **Evidence levels** are owned by FEAT-005. FEAT-006 only *reads* the assigned level to gate progression (§7).
- **Eight-axis ratings** are owned by FEAT-001 §10. FEAT-006 only *sequences* when they are performed.
- **Classification rules** are owned by FEAT-003. FEAT-006 only *sequences* when they are applied.
- **Implementation standards, code style, test frameworks** are owned by the codebase and future implementation-governance documents. FEAT-006 only *sequences* when implementation and testing occur.

---

## 3. Lifecycle Philosophy

### 3.1 Why deterministic sequencing is required

Without a fixed sequence, two sessions evaluating the same idea can pass it through governance in different orders, reach different conclusions, and produce inconsistent audit trails. A reproducible process requires a reproducible *order*. FEAT-006 makes the order canonical so that any observer, given the same idea, can predict which stages it has passed and which remain.

### 3.2 Why gates are sequential and non-skippable

Each stage produces an artefact that the next stage consumes. Skipping a stage leaves a gap in the audit chain that cannot be reconstructed after the fact. For example, evidence cannot be graded (Stage 4) without a classified submission (Stage 2); backtesting cannot be meaningful (Stage 10) without implementation (Stage 7) and unit tests (Stage 8) that establish the code is correct. The sequence is therefore not a preference — it is a dependency chain.

### 3.3 Why progression is evidence-capped

Not every idea deserves to reach every stage. An idea at FEAT-005 Level E is speculation and must be stopped early; an idea at Level D may be backtested but must not reach production. FEAT-006 enforces a **minimum evidence level at each stage** (§7) so that weak ideas are filtered cheaply, before they consume implementation, testing, or rollout effort. This cap is read from FEAT-005 and never overridden by FEAT-006.

### 3.4 Why rollback is a first-class stage

A feature that reaches production is not finished. Market conditions change, edge cases emerge, and dependencies drift. FEAT-004 §9 already defines rollback triggers and a one-line config-flag rollback mechanism. FEAT-006 elevates rollback from a feature-specific clause to a canonical stage (Stage 17), with deterministic triggers and targets, so that every future feature carries a defined escape path from the moment it enters production.

### 3.5 Why the lifecycle is implementation-independent

An idea can traverse Stages 1–6 — submission, classification, eight-axis evaluation, evidence grading, architecture review, and implementation approval — with **no production code existing**. This preserves FEAT-001's principle that design is separable from code, and that the owner writes all deterministic code (FEAT-001 §11).

---

## 4. Roles

Stages name a **Responsible Owner** drawn from this closed role set. In a personal-use system these roles may collapse to one individual, but they must remain **separable for audit purposes** — particularly the FEAT-005 two-reviewer independence requirement, which forbids the Proposer from also being an Evidence Reviewer on the same idea.

| Code | Role | Primary Stages |
| :--- | :--- | :--- |
| **P** | Proposer — originates and champions the idea | 1 |
| **CL** | Classifier — assigns and validates `COMP-*` / `SIT-*` tags per FEAT-003 | 2 |
| **EV** | Evaluator — performs the eight-axis rating per FEAT-001 §10 | 3 |
| **ER** | Evidence Reviewer — grades evidence per FEAT-005 (two independent reviewers) | 4 |
| **AR** | Architect — performs brownfield/architecture review per FEAT-003 Instruction 8 | 5 |
| **SO** | System Owner — the human decision-maker; sole authority for approvals and activation | 6, 13, 15 |
| **IM** | Implementer — writes deterministic code (FEAT-001 §11: the owner's responsibility) | 7 |
| **QA** | Validator — runs unit, integration, backtest, walk-forward, paper-trading validation | 8, 9, 10, 11, 12 |
| **MO** | Monitor — watches production metrics; human-in-the-loop per FEAT-001 §2 | 16, 17 |

---

## 5. Lifecycle Diagram

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                  RESEARCH IDEA LIFECYCLE (FEAT-006)                   │
 │           Deterministic, sequential, non-skippable stages.            │
 │           Each stage is a gate with entry & exit artefacts.           │
 └──────────────────────────────────────────────────────────────────────┘

  [DESIGN PHASE — no production code required]
  │
  1.  Idea Submitted                       ──► off-ramp: defer / archive
  │       (FEAT-003 §5 template)
  │
  2.  Component + Situation Classification ──► off-ramp: reject (new agent / redesign)
  │       (FEAT-002 codes, FEAT-003 Rules 1–4)
  │
  3.  Eight-Axis Evaluation                ──► off-ramp: defer (load-bearing axis = None)
  │       (FEAT-001 §10)
  │
  4.  Evidence Classification              ──► off-ramp: reject (Level E) / hold (Level D)
  │       (FEAT-005 Levels A–E)                 │
  │                                             └── Level sets progression ceiling (§7)
  │
  5.  Architecture Review                  ──► off-ramp: reject (unbounded / breaks hard filter)
  │       (FEAT-003 Instruction 8, brownfield)
  │
  6.  Implementation Approval              ──► off-ramp: defer (priority / scheduling)
  │       (System Owner sign-off)
  │
  [BUILD PHASE — production code begins]
  │
  7.  Implementation                       ──► loop back: on defect
  │       (deterministic code, owner-written)
  │
  8.  Unit Testing                         ──► loop back: on test failure
  │
  9.  Integration Testing                  ──► loop back: on integration failure
  │
  [VALIDATION PHASE — evidence accumulates; level may promote]
  │
  10. Backtesting                          ──► loop back on negative result
  │       (in-sample; may trigger D→C promotion per FEAT-005 §9)
  │
  11. Walk-Forward Validation              ──► loop back on failure / rollback trigger
  │       (out-of-sample, rolling)
  │
  12. Paper Trading                        ──► loop back on underperformance
  │       (simulated execution; no production effect)
  │
  [ROLLOUT PHASE — production environment]
  │
  13. Production Candidate                 ──► off-ramp: hold (not ready for shadow)
  │       (System Owner approval to deploy in shadow form)
  │
  14. Shadow Mode                          ──► loop back: anomaly → hold in shadow
  │       (production environment, ZERO score effect, log-only)
  │       (FEAT-004 §12 Stage A precedent)
  │
  15. Production Activation                ──► requires Level ≥ B
  │       (score effect ON; System Owner sign-off)
  │       (FEAT-004 §12 Stage B precedent)
  │
  [OPERATE PHASE]
  │
  16. Production Monitoring                ──► triggers Rollback (Stage 17) on breach
  │       (ongoing metric watch)
  │
  17. Rollback (if required)               ──► target per §9 (never forward)
        (config-flag disable; deterministic target by trigger type)
```

---

## 6. Stage Definitions

Every stage below specifies: Purpose, Inputs, Outputs, Entry Criteria, Exit Criteria, Responsible Owner, Failure Conditions, and Rollback Behaviour. Entry criteria are **conjunctive** — all must hold to enter. Exit criteria are **conjunctive** — all must hold to leave.

### Stage 1 — Idea Submitted

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Capture the idea in a structured, reviewable form. |
| **Inputs** | A natural-language idea from the Proposer. |
| **Outputs** | A completed FEAT-003 §5 Candidate Idea Submission Template, including idea type declaration (one of: `hard-filter`, `soft-score-factor`, `watch-only-signal`, `explanation-only`, `reject-or-defer`). |
| **Entry Criteria** | None — this is the lifecycle entry point. Any idea may be submitted. |
| **Exit Criteria** | (i) FEAT-003 §5 template fully populated; (ii) idea type declared; (iii) one-line plain-English description present (FEAT-001 §11.8). |
| **Responsible Owner** | Proposer (P) |
| **Failure Conditions** | Template incomplete; idea type undeclared; description absent. |
| **Rollback Behaviour** | Returned to Proposer for completion. No downstream effect. |

### Stage 2 — Component + Situation Classification

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Assign exactly one primary `COMP-*` and one primary `SIT-*` tag, validated against FEAT-003 Rules 1–4. |
| **Inputs** | The Stage 1 submission. |
| **Outputs** | Primary component tag, optional secondary component tag (≤ 1), primary situation tag, optional secondary situation tags (≤ 2), target implementation class named. |
| **Entry Criteria** | Stage 1 exit criteria met. |
| **Exit Criteria** | (i) Tags drawn from the FEAT-002 closed sets (no invented codes); (ii) tags validated by the FEAT-003 decision trees (FEAT-002 §4); (iii) target implementation class is an **existing** class (no new agent). |
| **Responsible Owner** | Classifier (CL) |
| **Failure Conditions** | Tag requires a new agent or new runtime component (FEAT-003 Instruction 8); tag is invented; idea is a full redesign rather than a bounded delta. → **Reject** (off-ramp). |
| **Rollback Behaviour** | Returned to Stage 1 for re-submission with corrected scope. |

### Stage 3 — Eight-Axis Evaluation

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Rate the idea on all eight FEAT-001 §10 axes (profitability impact, false-positive risk, false-negative risk, overfitting risk, data availability, implementation complexity, testability, explainability). |
| **Inputs** | The Stage 2 classified submission. |
| **Outputs** | An eight-axis rating table (each axis rated `High / Medium / Low / None`). |
| **Entry Criteria** | Stage 2 exit criteria met. |
| **Exit Criteria** | (i) All eight axes rated; (ii) no load-bearing axis rated `None` without a documented mitigation; (iii) required data and safe fallback stated (FEAT-001 §11.5–11.6). |
| **Responsible Owner** | Evaluator (EV) |
| **Failure Conditions** | A load-bearing axis (data availability, testability, or explainability) is rated `None` with no mitigation. → **Defer** (off-ramp). |
| **Rollback Behaviour** | Returned to Proposer to address the deficient axis. |

> **Consistency note:** FEAT-001 §10 states that "every future idea must be rated on all eight axes before it is considered for implementation." FEAT-006 fixes this rating at Stage 3, before evidence grading, which is fully consistent with FEAT-001's wording.

### Stage 4 — Evidence Classification

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Assign an Evidence Level (A–E) per FEAT-005, scoring the strength of supporting evidence. |
| **Inputs** | The Stage 3 submission with eight-axis rating; the evidence dossier (FEAT-005 §7). |
| **Outputs** | An Evidence Level (`A / B / C / D / E`) with a completed FEAT-005 §7 dossier and two-reviewer consensus (FEAT-005 §11). |
| **Entry Criteria** | Stage 3 exit criteria met. |
| **Exit Criteria** | (i) Level assigned via the FEAT-005 §5 rubric; (ii) dossier attached (FEAT-005 §7); (iii) two independent reviewers concur (FEAT-005 §11); (iv) re-evaluation triggers documented (FEAT-005 §12). |
| **Responsible Owner** | Evidence Reviewer (ER) — two independent reviewers |
| **Failure Conditions** | Level E assigned → **Reject** (off-ramp: brainstorming only, never implemented, FEAT-005 §4 Level E). Level D assigned → idea may proceed to architecture review but is **capped** at Stage 10 (research only; cannot reach shadow or production, FEAT-005 §4 Level D). |
| **Rollback Behaviour** | Level E rejected outright. Level D held: may progress only to backtesting, where a positive result can promote it to C (FEAT-005 §9.2). |

### Stage 5 — Architecture Review

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Verify the idea is a bounded delta, brownfield-safe, with a declared safe fallback, and that it requires no new agents. |
| **Inputs** | The Stage 4 graded submission; the FEAT-003 Instruction 8 non-redesign check. |
| **Outputs** | A signed architecture-review record: bounded-delta confirmation, brownfield-safety confirmation, safe-fallback confirmation. |
| **Entry Criteria** | (i) Stage 4 exit criteria met; (ii) Evidence Level ≥ D (Level E was rejected at Stage 4). |
| **Exit Criteria** | (i) Change confirmed as a bounded delta to one named component; (ii) no existing hard filter removed or weakened; (iii) Strict Buy Gate criteria not altered in a way that weakens it; (iv) safe fallback declared for every new data dependency; (v) no new agent required. |
| **Responsible Owner** | Architect (AR) |
| **Failure Conditions** | Change is unbounded; breaks a FEAT-001 §2 constraint; removes a hard filter; weakens the Gate; requires live LLM in the decision path. → **Reject** (off-ramp). |
| **Rollback Behaviour** | Returned to Stage 1 for re-scoping as a bounded delta. |

### Stage 6 — Implementation Approval

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Human-in-the-loop decision to authorise writing code (FEAT-001 §2). |
| **Inputs** | The Stage 5 approved submission. |
| **Outputs** | A signed implementation-approval record from the System Owner. |
| **Entry Criteria** | Stage 5 exit criteria met. |
| **Exit Criteria** | System Owner approval recorded with date and rationale. |
| **Responsible Owner** | System Owner (SO) |
| **Failure Conditions** | System Owner declines (priority, scheduling, or strategic reasons). → **Defer** (off-ramp). Not a rejection of the idea's merit. |
| **Rollback Behaviour** | Idea held in a deferred queue; resumes when the System Owner re-approves. |

### Stage 7 — Implementation

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Write the deterministic code delta (FEAT-001 §11.10: no live LLM in the decision path; owner-written). |
| **Inputs** | The Stage 6 approved submission; the target implementation class named at Stage 2. |
| **Outputs** | The code delta, including any config flags (following the FEAT-004 §5 config-flag precedent: a master `enabled` switch and a `stage` switch). |
| **Entry Criteria** | Stage 6 exit criteria met. |
| **Exit Criteria** | (i) Code delta merged behind a disabled config flag; (ii) a one-line rollback path exists (set `enabled = false`); (iii) no exceptions propagate to the recommendation path (FEAT-004 §7 boundary precedent). |
| **Responsible Owner** | Implementer (IM) |
| **Failure Conditions** | Code cannot be expressed as a bounded delta; requires architectural changes beyond the named component. → Loop back to Stage 5. |
| **Rollback Behaviour** | Defects loop back within Stage 7 until the delta is correct. The feature remains disabled by config throughout. |

### Stage 8 — Unit Testing

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Verify each function/branch of the delta in isolation with deterministic, fixed inputs. |
| **Inputs** | The Stage 7 code delta. |
| **Outputs** | A passing unit-test suite (deterministic: fixed inputs, fixed expected outputs; no live data — FEAT-004 §8 precedent). |
| **Entry Criteria** | Stage 7 exit criteria met. |
| **Exit Criteria** | (i) All unit tests pass; (ii) safe-fallback paths tested (every abstain/exception branch returns a defined safe value); (iii) no test depends on live data or network. |
| **Responsible Owner** | Validator (QA) |
| **Failure Conditions** | Any unit test fails; any fallback path raises instead of returning a safe value. → Loop back to Stage 7. |
| **Rollback Behaviour** | Code corrected in Stage 7; tests re-run. |

### Stage 9 — Integration Testing

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Verify the delta integrates with the existing pipeline without silent regression. |
| **Inputs** | The Stage 8 unit-tested delta; the existing pipeline. |
| **Outputs** | A passing integration-test suite confirming existing pipeline outputs are unchanged when the feature is disabled. |
| **Entry Criteria** | Stage 8 exit criteria met. |
| **Exit Criteria** | (i) With feature disabled, all existing recommendation outputs are byte-for-byte unchanged (backward compatibility, FEAT-001 §2); (ii) with feature enabled in shadow, no exception propagates past the feature boundary. |
| **Responsible Owner** | Validator (QA) |
| **Failure Conditions** | Existing outputs change when the feature is disabled (silent regression); an exception escapes the boundary. → Loop back to Stage 7. |
| **Rollback Behaviour** | Feature held disabled until integration is clean. |

### Stage 10 — Backtesting

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Validate the idea against historical data, in-sample, with a defined success/rollback metric set (FEAT-004 §9 precedent). |
| **Inputs** | The Stage 9 integrated delta; historical OHLCV (FEAT-001 §5). |
| **Outputs** | A backtest report: baseline-vs-treatment comparison, success metrics, rollback triggers. |
| **Entry Criteria** | (i) Stage 9 exit criteria met; (ii) Evidence Level ≥ D (Level E was rejected at Stage 4). |
| **Exit Criteria** | (i) All success metrics met or exceeded; (ii) no rollback trigger fired; (iii) baseline comparison documented. |
| **Responsible Owner** | Validator (QA) |
| **Failure Conditions** | Success metrics not met; rollback trigger fires (e.g., profit factor drops > 10% vs baseline, FEAT-004 §9). → **Loop back** to Stage 7 (the idea's parameters need revision). |
| **Rollback Behaviour** | **Promotion interaction:** a positive backtest result is the FEAT-005 §9.2 mechanism for D → C promotion. A Level D idea that passes Stage 10 promotes to Level C, unblocking Stages 11–14. A negative result returns the idea to Stage 7 and may trigger a FEAT-005 §12 RT-3 re-evaluation (downgrade). |

### Stage 11 — Walk-Forward Validation

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Validate out-of-sample, on rolling windows the backtest never saw (FEAT-004 §9 out-of-sample split). |
| **Inputs** | The Stage 10 backtested delta; out-of-sample data windows. |
| **Outputs** | A walk-forward report confirming the effect holds out-of-sample. |
| **Entry Criteria** | (i) Stage 10 exit criteria met; (ii) Evidence Level ≥ C (Level D was capped at Stage 10 and must have promoted). |
| **Exit Criteria** | (i) Out-of-sample metrics meet the same success bar as in-sample; (ii) no regime-specific collapse (effect must hold across ≥ 2 regimes per FEAT-005 Dimension 5). |
| **Responsible Owner** | Validator (QA) |
| **Failure Conditions** | Out-of-sample metrics collapse; effect is regime-specific (overfit). → **Loop back** to Stage 7; trigger FEAT-005 §12 RT-1/RT-2 re-evaluation. |
| **Rollback Behaviour** | Idea returns to research (Stage 4) if overfit is structural; returns to Stage 7 if tunable. |

### Stage 12 — Paper Trading

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Validate trade outcomes via **simulated execution** — no production pipeline, no real recommendations emitted. |
| **Inputs** | The Stage 11 walk-forward-validated delta; a simulated execution harness. |
| **Outputs** | A paper-trading report over a defined observation window. |
| **Entry Criteria** | (i) Stage 11 exit criteria met; (ii) Evidence Level ≥ C. |
| **Exit Criteria** | (i) Simulated outcomes stable over the observation window; (ii) no sustained underperformance vs the walk-forward expectation. |
| **Responsible Owner** | Validator (QA) |
| **Failure Conditions** | Sustained simulated underperformance. → **Loop back** to Stage 7; trigger FEAT-005 §12 RT-4 re-evaluation. |
| **Rollback Behaviour** | Idea returns to research (Stage 4) or Stage 7 depending on whether the failure is evidential or parametric. |

> **Distinction (load-bearing):** Paper Trading (Stage 12) is **simulated** execution outside the production pipeline. Shadow Mode (Stage 14) is the **production** pipeline with **zero score effect**. These must never be conflated (Architecture Review §6.2).

### Stage 13 — Production Candidate

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | System Owner approval to deploy the feature into the production pipeline **in shadow form** (zero score effect). |
| **Inputs** | The Stage 12 paper-trading report; the full validation chain (Stages 8–12). |
| **Outputs** | A signed production-candidate approval. |
| **Entry Criteria** | (i) Stage 12 exit criteria met; (ii) Evidence Level ≥ C; (iii) System Owner review of the validation chain. |
| **Exit Criteria** | System Owner approval recorded with date, rationale, and the shadow observation-window plan (minimum session count). |
| **Responsible Owner** | System Owner (SO) |
| **Failure Conditions** | System Owner declines to deploy. → **Hold** (off-ramp); idea remains paper-trading-validated but not deployed. |
| **Rollback Behaviour** | Held until re-approved; no production effect. |

### Stage 14 — Shadow Mode

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Run the feature inside the **production** pipeline with **zero** score effect and **zero** label change — logging only (FEAT-004 §12 Stage A precedent). |
| **Inputs** | The Stage 13 approved delta; production data. |
| **Outputs** | A populated per-stock log payload (FEAT-004 §8 schema precedent) over the shadow observation window. |
| **Entry Criteria** | (i) Stage 13 exit criteria met; (ii) Evidence Level ≥ C; (iii) feature deployed with `stage = SHADOW`, `enabled = true`. |
| **Exit Criteria** | (i) Shadow observation window completed (minimum session count, FEAT-004 §12: ≥ 30 sessions); (ii) log payload present on every processed stock; (iii) shadow-period metrics correlate as predicted (e.g., penalised regimes show higher false-positive rates); (iv) no unhandled exception propagated. |
| **Responsible Owner** | Validator (QA) + Monitor (MO) |
| **Failure Conditions** | Feature mis-fires in shadow (e.g., downgrades or penalises in FAVORABLE regime — FEAT-004 §9); exception propagates; log payload incomplete. → **Hold in shadow** (do not activate); fix in Stage 7; re-run shadow. |
| **Rollback Behaviour** | `stage` held at `SHADOW`. Activation (Stage 15) blocked until shadow exit criteria are met. |

### Stage 15 — Production Activation

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Turn the score effect ON (FEAT-004 §12 Stage B precedent). |
| **Inputs** | The Stage 14 shadow report confirming all shadow exit criteria. |
| **Outputs** | Feature running with `stage = ACTIVE`; score effect applied per spec. |
| **Entry Criteria** | (i) Stage 14 exit criteria met; (ii) **Evidence Level ≥ B** (Level C is **not** activation-eligible per FEAT-005 §4 — Level C is shadow-only until promoted); (iii) System Owner sign-off. |
| **Exit Criteria** | (i) Activation recorded with date and System Owner sign-off; (ii) first-session post-activation metrics within expected bounds. |
| **Responsible Owner** | System Owner (SO) |
| **Failure Conditions** | Evidence Level still C at activation time → **blocked** (must promote C → B per FEAT-005 §9 before activation). |
| **Rollback Behaviour** | If first-session metrics breach, immediately revert to Shadow Mode (Stage 14) via one-line config change. |

> **Promotion interaction:** Level C → B promotion (FEAT-005 §9.2) requires "≥ 2 independent confirmations or wider practitioner adoption." The shadow-period correlations (Stage 14) can serve as one such confirmation when documented and independently reviewed.

### Stage 16 — Production Monitoring

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Continuously watch the activated feature against its rollback-trigger metric set (FEAT-004 §9 precedent). |
| **Inputs** | Live production metrics; the feature's defined rollback triggers. |
| **Outputs** | An ongoing monitoring record; breach alerts. |
| **Entry Criteria** | Stage 15 exit criteria met. |
| **Exit Criteria** | None — this is a steady-state stage. It persists for the lifetime of the feature. |
| **Responsible Owner** | Monitor (MO) |
| **Failure Conditions** | Any rollback trigger fires (§9). → Invoke Stage 17. |
| **Rollback Behaviour** | Hands off to Stage 17 on breach. |

### Stage 17 — Rollback (if required)

| Attribute | Definition |
| :--- | :--- |
| **Purpose** | Deterministically revert the feature to a safe state when a monitoring trigger fires. |
| **Inputs** | The breach signal from Stage 16; the rollback-target rules (§9). |
| **Outputs** | A rollback record: trigger, target state, timestamp, config change applied. |
| **Entry Criteria** | A Stage 16 rollback trigger has fired. |
| **Exit Criteria** | (i) Feature reverted to its rollback target (§9); (ii) recommendation outputs returned to pre-feature behaviour; (iii) rollback recorded in the audit trail. |
| **Responsible Owner** | System Owner (SO) + Monitor (MO) |
| **Failure Conditions** | Rollback itself fails to restore pre-feature behaviour (the one-line config disable did not take effect). → Manual intervention; feature treated as a production incident. |
| **Rollback Behaviour** | Rollback is always to the most recent safe state, **never forward**. After rollback, the idea returns to research (Stage 4 re-evaluation) or Stage 7 (parametric revision) per §9. |

---

## 7. Lifecycle Decision Rules

These rules make progression deterministic. They are conjunctive and admit no discretion.

### 7.1 Forward progression rules

| Rule | Statement |
| :--- | :--- |
| **DR-1** | Progression is strictly sequential: Stage N → Stage N+1 only. No skipping. |
| **DR-2** | Every stage's exit criteria must be fully met before the next stage begins. Partial completion does not advance. |
| **DR-3** | Every stage produces a named, dated, append-only audit artefact (§10). An idea with a missing artefact cannot advance. |
| **DR-4** | The Evidence Level assigned at Stage 4 sets a **ceiling** on progression, enforced as a minimum level at each downstream stage (§7.2). |
| **DR-5** | Evidence Level may rise during the lifecycle (via FEAT-005 §9 promotion at Stages 10/14) and **unblocks** further progression. It may also fall (via FEAT-005 §12 triggers), which **re-blocks** downstream stages. |
| **DR-6** | The System Owner (SO) is the sole authority for Stages 6, 13, and 15. No automated activation is permitted (FEAT-001 §2: human-in-the-loop). |
| **DR-7** | Rollback (Stage 17) targets are determined solely by which trigger fired (§9). The target is always backward, never forward. |

### 7.2 Minimum Evidence Level per stage (the progression ceiling)

| Stage | Minimum Evidence Level to enter | Source |
| :--- | :--- | :--- |
| 1–3 | Any (including E) | — |
| 4 | Any (E is rejected here) | FEAT-005 §4 Level E |
| 5–9 | ≥ D | FEAT-005 §4 Level D: research + testable |
| 10 (Backtesting) | ≥ D | FEAT-005 §4 Level D: "backtest is the mandatory next step" |
| 11 (Walk-Forward) | ≥ C | FEAT-005 §4 Level D: "no walk-forward possible at this level" |
| 12 (Paper Trading) | ≥ C | FEAT-005 §4 Level C: shadow-eligible |
| 13 (Production Candidate) | ≥ C | FEAT-005 §4 Level C: shadow-eligible only |
| 14 (Shadow Mode) | ≥ C | FEAT-005 §4 Level C: shadow-eligible only |
| 15 (Production Activation) | ≥ B | FEAT-005 §4 Level C: "not production-eligible until promoted to B" |
| 16 (Production Monitoring) | ≥ B | Inherited from Stage 15 |
| 17 (Rollback) | n/a | Triggered reactively |

### 7.3 Conservative tie-break

Where any criterion is ambiguous or two reviewers disagree, the **more conservative** outcome applies: defer rather than advance; lower evidence level rather than higher; rollback rather than hold. This mirrors FEAT-004 §4 ("when in doubt, be conservative") and FEAT-005 §5.4.

---

## 8. Off-Ramps

An idea may leave the forward lifecycle at defined points. Each off-ramp has a deterministic meaning and a defined re-entry path.

| Off-Ramp | Meaning | Where it can occur | Re-entry path |
| :--- | :--- | :--- | :--- |
| **Reject** | The idea is fundamentally invalid: violates a FEAT-001 §2 constraint, requires a new agent (FEAT-003 Instruction 8), is a redesign rather than a bounded delta, or is graded Level E (FEAT-005). | Stages 2, 4, 5 | None as the same idea. Must be rewritten as a **new** submission re-entering at Stage 1. |
| **Defer** | The idea is valid but blocked: priority, scheduling, data unavailable, or a load-bearing axis rated `None` pending mitigation. | Stages 1, 3, 6, 13 | Resumes at the same stage when the blocker clears. No re-validation of earlier stages required unless a FEAT-005 §12 trigger fired during the hold. |
| **Archive** | Terminal state for completed (monitored, stable) or rejected ideas. Append-only. | Any, terminally | Archived ideas are reference material only. A descendant idea re-enters at Stage 1 as a new submission, citing the archive entry. |
| **Return to research** | The idea is valid in form but its evidence or parameters are insufficient. Sent back to accumulate evidence or revise parameters. | Stages 10, 11, 12, 16, 17 | Returns to Stage 4 (evidence re-grading) if evidential, or Stage 7 (parametric revision) if tunable. The destination is recorded in the audit trail. |

### 8.1 Off-ramp decision rule

```
Did the idea violate a FEAT-001 §2 constraint, require a new agent,
   or grade Level E?
 ├── YES ──► REJECT (re-enter only as a new submission)
 └── NO
      │
      Is the idea blocked by an external factor (priority, data, scheduling)?
       ├── YES ──► DEFER (resume at same stage when cleared)
       └── NO
            │
            Did validation (Stages 10–12) or monitoring (Stage 16) fail?
             ├── YES ──► RETURN TO RESEARCH (Stage 4 or Stage 7)
             └── NO ──► Continue forward progression
```

---

## 9. Rollback Rules

Rollback is deterministic: the trigger determines the target. There is no discretion and no forward rollback.

### 9.1 Rollback trigger → target matrix

| Trigger (fired at) | Source precedent | Rollback target | Action |
| :--- | :--- | :--- | :--- |
| Monitoring metric breach (Stage 16): missed-winner rate ↑ > 8% out-of-sample | FEAT-004 §9 | Shadow Mode (Stage 14) | Set `stage = SHADOW`; score effect OFF; logging continues |
| Monitoring metric breach (Stage 16): profit factor drops > 10% vs baseline | FEAT-004 §9 | Shadow Mode (Stage 14) | Set `stage = SHADOW` |
| Feature mis-fires in FAVORABLE regime (downgrades/penalises when it should not) | FEAT-004 §9 | Shadow Mode (Stage 14) | Set `stage = SHADOW`; bug-fix in Stage 7 |
| Unhandled exception propagates past the feature boundary | FEAT-004 §7 | Shadow Mode (Stage 14) or full disable | Set `enabled = false` if boundary failure is severe |
| Backtest negative result (Stage 10) | FEAT-005 §12 RT-3 | Stage 7 (parametric revision) | Revise parameters; re-backtest |
| Walk-forward collapse / overfit (Stage 11) | FEAT-005 §12 RT-1/RT-2 | Stage 4 (evidence re-grading) or Stage 7 | Re-evaluate evidence; revise |
| Paper-trading underperformance (Stage 12) | FEAT-005 §12 RT-4 | Stage 7 | Revise; re-paper-trade |
| Evidence source retracted (any time) | FEAT-005 §12 RT-6 | Stage 4 | Re-grade; level may drop, re-blocking downstream stages |
| Market-structure change invalidates evidence (any time) | FEAT-005 §12 RT-5 | Stage 4 | Re-grade |

### 9.2 Rollback invariants

| Invariant | Statement |
| :--- | :--- |
| **RI-1** | Rollback is always achievable by a **one-line config change** (`enabled = false` or `stage = SHADOW`). No code change is required to roll back (FEAT-004 §9 precedent). |
| **RI-2** | Rollback never moves an idea forward. |
| **RI-3** | After rollback, recommendation outputs must return to pre-feature behaviour. This is verified, not assumed. |
| **RI-4** | Every rollback is recorded in the audit trail (§10) with trigger, target, timestamp, and the config change applied. |
| **RI-5** | A rolled-back feature may re-advance only by re-passing the stage it was rolled back to, including any FEAT-005 re-grading required by a §12 trigger. |

---

## 10. Lifecycle Audit Requirements

Every stage produces a mandatory, append-only audit artefact. The complete chain is the idea's audit trail. An idea with a broken chain (missing artefact) cannot advance or be activated.

### 10.1 Mandatory artefacts per stage

| Stage | Mandatory artefact | Format |
| :--- | :--- | :--- |
| 1 | Submission record | FEAT-003 §5 template |
| 2 | Classification record | `COMP-*` / `SIT-*` tags + validation against FEAT-003 decision trees |
| 3 | Eight-axis rating | FEAT-001 §10 table (all eight axes) |
| 4 | Evidence dossier + level | FEAT-005 §7 template + two-reviewer consensus |
| 5 | Architecture review | Bounded-delta / brownfield / safe-fallback sign-off |
| 6 | Implementation approval | System Owner sign-off with date + rationale |
| 7 | Implementation record | Code delta reference + config-flag definition + rollback path |
| 8 | Unit-test report | Pass/fail per test + fallback-path coverage |
| 9 | Integration-test report | Disabled-feature backward-compatibility confirmation |
| 10 | Backtest report | Baseline-vs-treatment metrics + success/rollback verdict |
| 11 | Walk-forward report | Out-of-sample metrics + regime-coverage confirmation |
| 12 | Paper-trading report | Observation window + outcome stability |
| 13 | Production-candidate approval | System Owner sign-off + shadow-window plan |
| 14 | Shadow report | Log-payload completeness + shadow-window correlations |
| 15 | Activation record | System Owner sign-off + date + first-session metrics |
| 16 | Monitoring record | Ongoing; breach alerts |
| 17 | Rollback record | Trigger + target + timestamp + config change |

### 10.2 Audit-trail invariants

- **Append-only.** No artefact is deleted or overwritten. Corrections are new entries that reference the corrected entry.
- **Self-contained.** Each artefact is understandable without the others, but together they form a complete chain from submission to monitoring.
- **Reproducible.** Given the artefact chain, a third party can reconstruct the idea's entire journey and verify that no stage was skipped.
- **Cross-referenced.** Evidence-level changes (FEAT-005 promotions/downgrades) are recorded both in the FEAT-005 dossier and in the lifecycle audit trail at the stage where they occurred.

---

## 11. Governance Integration

This section shows precisely how FEAT-006 consumes each existing governance document without replacing any of it.

| Existing document | What FEAT-006 consumes | At which stage | What FEAT-006 does NOT redefine |
| :--- | :--- | :--- | :--- |
| **FEAT-001** | §2 constraints; §8 known gaps; §10 eight axes; §11 output rules | 1, 2, 3, 5 | Constraints, gaps, the eight axes themselves, output rules |
| **FEAT-002** | `COMP-*` / `SIT-*` closed vocabularies | 2 | The tag sets; tagging rules |
| **FEAT-003** | §5 submission template; Rules 1–4; Instruction 8 | 1, 2, 5 | The template; the classification rules; the non-redesign rule |
| **FEAT-005** | Levels A–E; §5 rubric; §7 dossier; §9 promotion; §12 triggers | 4, 10, 14, 15, 16, 17 | The levels; the scoring rubric; the promotion/downgrade mechanics |
| **FEAT-004** | Shadow→active→rollback as the precedent | 13, 14, 15, 16, 17 | FEAT-004's specific thresholds, deltas, and logic |

### 11.1 Ordering reconciliation

FEAT-006 fixes the eight-axis evaluation (Stage 3) **before** evidence classification (Stage 4). This is consistent with FEAT-001 §10, which states the eight axes are required "before an idea is considered for implementation" — it does not fix their position relative to evidence grading, which did not exist until FEAT-005. FEAT-006 therefore refines, and does not contradict, FEAT-001 §10. No edit to FEAT-001 is required.

### 11.2 Evidence-ceiling reconciliation

FEAT-006 reads the FEAT-005 level as a progression ceiling (§7.2). It does not modify the level or the rubric. When an idea promotes (e.g., D → C at Stage 10), the promotion is performed by FEAT-005 §9 mechanics; FEAT-006 only *observes* the new level and re-evaluates the ceiling.

---

## 12. Worked Example — FEAT-004 Through the Lifecycle

This example traces FEAT-004 (Market Regime Overlay) through the lifecycle, marking each stage as completed (evidenced in the FEAT-004 documents), in progress, or required-next.

| Stage | Status | Evidence |
| :--- | :--- | :--- |
| 1. Idea Submitted | ✅ Completed | FEAT-004 Spec §"Candidate Idea Submission": idea name, one-line description, idea type (soft-score-factor + optional watch-only-signal) all present. |
| 2. Classification | ✅ Completed | Primary `COMP-REC`, secondary `None`, primary `SIT-BMR`, secondary `SIT-SR`. Justified in Spec §1 against FEAT-003 Rule 3 (Gating Order). Target class `RecommendationAgent` (existing). No new agent — `SectorStrengthHelper` is a utility, not an agent (Spec §11). |
| 3. Eight-Axis Evaluation | ⚠️ Required | Not explicitly tabulated in the FEAT-004 spec. Must be completed as a Stage 3 artefact: data availability = High (benchmark OHLCV already in FEAT-001 §5); testability = High (deterministic); explainability = High (logged regime state); overfitting risk = Medium (the -3.0/-5.0 deltas are unvalidated). |
| 4. Evidence Classification | ✅ Completed (graded) | Per FEAT-005 §13 Example 2: **Level C** (total score 48). Concept well-supported; specific deltas single-party. Dossier required per FEAT-005 §7. |
| 5. Architecture Review | ✅ Completed | Spec §11 Brownfield Safety Confirmation: bounded delta ✅, no hard filters weakened ✅, Gate criteria unchanged ✅, no new agents ✅, safe fallback (ABSTAINED) ✅, no exception propagation ✅, one-line rollback ✅. |
| 6. Implementation Approval | ✅ Completed | Spec header: "Status: Ready for implementation." System Owner sign-off implied by document publication. |
| 7. Implementation | 🔄 Pre-implementation | Implementation Breakdown exists ("Pre-implementation task breakdown. No production code.") — the design is complete; the code delta is not yet written. Config flags defined (Breakdown §5). |
| 8. Unit Testing | ⏳ Required next | Breakdown §8 defines a 20-test plan (deterministic, fixed inputs). To be executed once Stage 7 lands. |
| 9. Integration Testing | ⏳ Required | Disabled-feature backward compatibility to be verified. |
| 10. Backtesting | ⏳ Required | Spec §9 defines the data split (in-sample A/B/C, out-of-sample) and success metrics (false-positive reduction ≥ 5%, missed-winner ≤ 3%, etc.). Eligible: Level C ≥ the Stage 10 minimum (≥ D). |
| 11. Walk-Forward Validation | ⏳ Required | Spec §9 out-of-sample window (2023-01 to 2024-06). Eligible: Level C ≥ the Stage 11 minimum (≥ C). |
| 12. Paper Trading | ⏳ Required | Simulated execution validation. |
| 13. Production Candidate | ⏳ Required | System Owner approval to shadow. |
| 14. Shadow Mode | ⏳ Required (per Spec §12 Stage A) | Minimum 30 trading sessions, log-only, zero score effect. Spec §12 mandates this explicitly. |
| 15. Production Activation | ⚠️ Gated | Requires **Level ≥ B**. FEAT-004 is currently Level C. **Activation is blocked** until FEAT-004 promotes C → B (FEAT-005 §9.2: ≥ 2 independent confirmations). The shadow-period correlations from Stage 14 can serve as one confirmation when independently reviewed. |
| 16. Production Monitoring | ⏳ Required post-activation | Spec §9 rollback criteria define the monitoring triggers. |
| 17. Rollback | ⏳ Conditional | Spec §9 defines rollback triggers and the one-line `feat004.enabled = false` mechanism. |

### 12.1 Key finding from the trace

FEAT-004 is presently **between Stages 6 and 7** — approved for implementation, design complete, code not yet written. The lifecycle exposes one critical gate: **FEAT-004 cannot activate (Stage 15) at its current Level C.** It must either (a) promote to Level B before activation, or (b) remain indefinitely in shadow. This is the lifecycle enforcing FEAT-005's progression ceiling exactly as designed — and it is consistent with FEAT-004's own conservative shadow-first mandate.

---

## 13. Brownfield Safety Confirmation

FEAT-006 is a governance document. It touches no runtime code. The following invariants are confirmed.

| Constraint | Status |
| :--- | :--- |
| No existing FEAT-001 through FEAT-005 document is modified | ✅ Confirmed — FEAT-006 consumes them by reference only |
| No new `COMP-*` component tags introduced | ✅ Confirmed |
| No new `SIT-*` situation tags introduced | ✅ Confirmed |
| No new evidence levels introduced | ✅ Confirmed — Levels A–E owned entirely by FEAT-005 |
| The eight-axis evaluation is not redefined | ✅ Confirmed — owned by FEAT-001 §10; only sequenced |
| No new runtime agents or runtime components | ✅ Confirmed — FEAT-006 is a process spine, not code |
| No live LLM inference introduced anywhere | ✅ Confirmed — every gate is artefact-based |
| Deterministic: same idea + same artefacts → same stage verdict | ✅ Confirmed — enforced by §7 decision rules and §10 audit trail |
| Backward compatible with the existing pipeline | ✅ Confirmed — no pipeline stage, threshold, or Gate is altered |
| No known gap (FEAT-001 §8) re-raised as a new discovery | ✅ Confirmed |
| Rollback requires no code change | ✅ Confirmed — one-line config flag per RI-1 |
| Implementation-independent | ✅ Confirmed — Stages 1–6 traversable with no production code |
| Single responsibility preserved | ✅ Confirmed — FEAT-006 sequences only; it does not grade, classify, or score |

---

## 14. Future Extensions

The following governance documents may extend the lifecycle in the future. They are **identified only** — not defined, not committed, and not to be assumed present.

| Candidate future document | Lifecycle stages it would govern | Why it is not part of FEAT-006 |
| :--- | :--- | :--- |
| **Backtesting Standards** | Stage 10 | FEAT-006 sequences backtesting but does not define success metrics, data-split rules, or slippage models. FEAT-004 §9 is a feature-specific precedent, not a general standard. |
| **Walk-Forward Standards** | Stage 11 | Window sizing, anchoring method, and regime-coverage thresholds are not generalised here. |
| **Paper-Trading Standards** | Stage 12 | Simulation harness requirements and observation-window definitions are not generalised here. |
| **Production Monitoring Standards** | Stage 16 | Metric thresholds, alerting, and review cadence are not generalised here; FEAT-006 only mandates that monitoring exists. |
| **Implementation / Code Standards** | Stages 7–9 | Code style, test frameworks, and review process are owned by the codebase, not by the Research OS. |

Each of these, if created, would slot into the lifecycle at the named stages **without modifying FEAT-006** — they would be consumed by reference, exactly as FEAT-006 consumes FEAT-001 through FEAT-005.

---

## 15. Final Recommendation

**Adopt FEAT-006 v1.0 as the canonical Research Idea Lifecycle for all future trading recommendation enhancements.**

Application guidance:

1. **Effective immediately**, no future feature may advance to implementation (Stage 7) without a complete audit trail for Stages 1–6. An idea with a broken chain is held at its last completed stage.
2. **The seventeen stages are closed and ordered.** No skipping, no reordering. The only permitted deviations are the defined off-ramps (§8) and rollback paths (§9).
3. **The evidence ceiling (§7.2) is non-negotiable.** A Level C idea cannot activate; a Level D idea cannot shadow. These caps are read from FEAT-005 and enforced by FEAT-006 — never overridden locally.
4. **FEAT-004 is the reference instance.** Its shadow→active→rollback design (Spec §12, §9) is the concrete pattern that Stages 14–17 generalise. Future features should mirror its config-flag, safe-fallback, and double-try/except patterns.
5. **The System Owner is the sole human gate** at Stages 6, 13, and 15. No automated activation is permitted (FEAT-001 §2: human-in-the-loop, no auto-execution).
6. **Rollback is always one config line away** (RI-1). Every feature must ship with a master `enabled` switch and a `stage` switch from Stage 7 onward, so that Stages 14, 15, and 17 are config-only operations.
7. **The audit trail is append-only and self-contained** (§10). It is the mechanism that makes the lifecycle reproducible and auditable — the two properties, alongside determinism and brownfield safety, that the entire Research Operating System exists to guarantee.

FEAT-006 is the fifth governance layer of the Research Operating System. It does not evaluate, classify, score, or grade — those belong to FEAT-001 through FEAT-005. It answers one question only: ***in what order, and through which gates, does an idea travel from a written proposal to a monitored production feature?*** It makes that order canonical so that every idea, in every session, follows the same reproducible path.

---

*End of RESEARCH_IDEA_LIFECYCLE v1.0 — FEAT-006 Baseline*
