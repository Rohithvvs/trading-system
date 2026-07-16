# EVIDENCE_HIERARCHY — Evidence Classification Framework
**Version:** 1.0 — FEAT-005 Baseline
**Date:** 2026-07-11
**Scope:** This document defines the deterministic evidence classification framework that every future trading recommendation enhancement must pass before implementation. It governs **evidence quality only**. It does not govern implementation, architecture, coding, backtesting execution, walk-forward execution, or production rollout — those belong to future governance documents.

---

## 1. Purpose

The Research Operating System already enforces *what* an idea modifies (`COMP-*`), *where* it applies (`SIT-*`), and *how* it is submitted (FEAT-003 §5 template). It does not yet enforce *how well-proven* an idea must be before it is allowed to consume engineering time or touch production.

FEAT-005 closes that gap. It introduces a single, deterministic, five-level scale — `Level A` through `Level E` — that scores the **strength of supporting evidence** behind an idea. Every future feature, indicator, filter, weight change, or rule modification must carry an Evidence Level before it may be discussed for implementation.

This document governs **evidence quality only**. It explicitly does **not** govern:

- Implementation quality or code style
- Profitability or expected return
- Engineering effort or scheduling
- Business value or user demand
- Backtesting execution methodology
- Walk-forward validation execution
- Production rollout sequencing

These belong to future governance documents and to the existing pipeline constraints in FEAT-001 §2.

---

## 2. Position Within the Research Operating System

FEAT-005 is a **governance document**, sibling to FEAT-001, FEAT-002, and FEAT-003. It is **not** a feature specification like FEAT-004. It introduces no runtime behavior, no production code, no new agents, and no new runtime components.

### 2.1 Dependency map

```
FEAT-001  Shared Context Pack          (truth: architecture, constraints, gaps)
   │
FEAT-002  Component × Situation        (vocabulary: COMP-*, SIT-*)
   │
FEAT-003  Classification Rulebook      (validation rules + submission template)
   │
FEAT-005  Evidence Hierarchy           ← THIS DOCUMENT (evidence strength: A–E)
   │
FEAT-004  Market Regime Overlay        (first FEATURE — retrospectively gradeable)
   │
Future features                        (each must carry an Evidence Level)
```

### 2.2 Integration with each existing document

| Document | Relationship | What FEAT-005 consumes from it | What FEAT-005 changes about it |
| :--- | :--- | :--- | :--- |
| **FEAT-001** | Consumes | §2 constraints (determinism, brownfield safety, no live LLM); §8 known gaps (referenced by number in examples); §10 eight evaluation axes (preserved as a *separate, later* gate) | **Nothing.** FEAT-001 is untouched. |
| **FEAT-002** | Consumes | The closed `COMP-*` and `SIT-*` vocabularies, used in worked examples | **Nothing.** FEAT-005 introduces no new tags. Evidence Level is orthogonal to the tag grammar. |
| **FEAT-003** | Consumes | The §5 Candidate Idea Submission Template — Evidence Level attaches to this template as an additional field | **Nothing.** The template is extended by reference, not rewritten. |
| **FEAT-004** | Uses as worked example | FEAT-004 is retrospectively gradeable as a sample feature under the evidence scale | **Nothing.** FEAT-004 remains the first concrete feature. |

### 2.3 Orthogonality statement

Evidence Level is an **independent governance attribute** of an idea. It is **not**:

- A Component Tag (`COMP-*`)
- A Situation Tag (`SIT-*`)
- A Runtime State (e.g., `FAV`, `NEU`, `CAU`, `DEF`, `ABS`)
- A Recommendation Score (the 100-point technical score, the composite score)
- A Production Status (e.g., `SHADOW`, `ACTIVE`)

It does not modify any of those. It is a scalar attribute `A | B | C | D | E` attached at design time to the FEAT-003 submission, evaluated against documented artefacts, and re-evaluated on defined triggers (§12).

---

## 3. Evidence Philosophy

Evidence quality is evaluated **separately** from four other concerns that are easy to conflate with it. The separation is mandatory and must be preserved by every reviewer.

### 3.1 Evidence quality ≠ implementation quality

An idea may have impeccable supporting evidence (Level A) and still be implemented poorly. Conversely, an idea may be implemented cleanly and rest on no evidence (Level E). Evidence grading judges the *claim*, not the *code*. Code does not exist at evidence-grading time.

### 3.2 Evidence quality ≠ profitability

An idea may be strongly supported by academic literature and still lose money in this specific market, with this specific universe (NIFTY 500), under this specific execution model (human-in-the-loop, no auto-execution). Profitability is established by backtesting and walk-forward validation — **future governance documents**, not FEAT-005. FEAT-005 grades whether the idea is *worth testing*, not whether it will *pay off*.

### 3.3 Evidence quality ≠ engineering effort

An idea may be a one-line config change and still require Level A evidence before it touches a threshold that gates real money (e.g., changing the BUY threshold from 72 to 78). Conversely, an idea may be expensive to build and rest on Level C evidence. Effort is a scheduling concern, not an evidence concern.

### 3.4 Evidence quality ≠ business value

User demand, dashboard polish, and stakeholder preference do not constitute evidence. An idea that "the user really wants" but has no supporting evidence is still Level E and must be promoted through evidence accumulation, not through priority pressure.

### 3.5 Core principle

> Evidence quality answers one question only: **"How well-proven is the claim that this idea does what it says, independent of this codebase?"** FEAT-005 makes that question answerable by two independent reviewers who must reach the same verdict from the same artefacts.

---

## 4. Five Evidence Levels

Exactly five levels. Evaluated top-to-bottom: the **highest** level whose acceptance criteria are **all** met is the assigned level. First-match-wins is not used here (unlike FEAT-004 §4) — the highest-qualifying level wins, because levels are cumulative.

### Level A — Academically Proven

| Attribute | Definition |
| :--- | :--- |
| **Definition** | The claim is established in peer-reviewed academic literature, replicated independently, and supported by strong statistical evidence across multiple market regimes. |
| **Acceptance Criteria** | (i) ≥ 3 independent peer-reviewed sources; (ii) at least one independent replication; (iii) statistically significant effect size reported; (iv) no uncontested contradictory peer-reviewed evidence; (v) effect demonstrated out-of-sample in the literature. |
| **Required Supporting Material** | Full bibliographic citations (author, year, journal/venue, DOI or stable URL); replication studies; reported effect sizes and confidence intervals; sample periods used. |
| **Required Documentation** | Literature review dossier (see §8 template) cross-referencing each acceptance criterion to its source. |
| **Required Validation** | Academic out-of-sample evidence accepted as the primary proof. A local backtest is still required by future implementation-governance documents before the idea may touch production. |
| **Allowed Usage** | Production-eligible. May enter shadow mode once implementation gates (future governance) are passed. |
| **Risk Level** | **Low.** The claim is the least likely to be a statistical artefact. |
| **Promotion Eligibility** | Terminal level. There is no Level above A. |
| **Downgrade Conditions** | (i) A cited source is formally retracted; (ii) a new peer-reviewed study fails to replicate across multiple attempts; (iii) the claimed effect is shown to be regime-specific to a market that no longer exists. |

### Level B — Professionally Established

| Attribute | Definition |
| :--- | :--- |
| **Definition** | The claim is widely used by professional traders, supported by multiple practical implementations, and backed by good historical evidence (but not necessarily peer-reviewed academic proof). |
| **Acceptance Criteria** | (i) ≥ 3 independent practitioner or textbook sources; (ii) documented historical performance track record; (iii) implemented in ≥ 2 independent trading systems or platforms; (iv) no major contradictory practitioner consensus. |
| **Required Supporting Material** | Textbook or professional references (author, title, year, publisher); documented historical track records; named systems or platforms that implement the technique. |
| **Required Documentation** | Practitioner evidence dossier (see §8 template) listing each source and the historical performance claim it makes. |
| **Required Validation** | A local backtest is **mandatory**. Walk-forward validation is **recommended**. Both belong to future implementation-governance documents, not to FEAT-005. |
| **Allowed Usage** | Production-eligible after shadow mode and validation gates pass. |
| **Risk Level** | **Low–Medium.** The technique is battle-tested in practice but may not have formal statistical proof. |
| **Promotion Eligibility** | Promotable to **Level A** if peer-reviewed academic replication is subsequently published. |
| **Downgrade Conditions** | (i) Contradictory peer-reviewed evidence emerges; (ii) sustained documented underperformance across multiple independent practitioners; (iii) the underlying market structure the technique relied on changes (e.g., a regulatory shift in STT or settlement). |

### Level C — Logically Sound, Partially Validated

| Attribute | Definition |
| :--- | :--- |
| **Definition** | The claim rests on strong logical reasoning and has some empirical evidence, but validation is limited and not yet widely replicated. |
| **Acceptance Criteria** | (i) A coherent logical or first-principles derivation of the expected effect; (ii) ≥ 1 empirical study or internal analysis showing the effect exists; (iii) no decisive contradictory evidence; (iv) the mechanism is plausible under the FEAT-001 §3 architecture. |
| **Required Supporting Material** | The logical derivation; the single empirical result (with sample period and metric); a statement of why broader validation is not yet available. |
| **Required Documentation** | Reasoning dossier (see §8 template) including the derivation and the preliminary evidence with all its limitations stated. |
| **Required Validation** | A local backtest is **mandatory**. Walk-forward validation is **mandatory**. Paper trading is **recommended**. All belong to future implementation-governance documents. |
| **Allowed Usage** | Shadow-mode-eligible only. **Not** production-eligible until promoted to Level B and until implementation-governance gates pass. |
| **Risk Level** | **Medium.** The effect may be real or may be a single-sample artefact. |
| **Promotion Eligibility** | Promotable to **Level B** with wider practitioner adoption or ≥ 2 additional independent empirical confirmations. |
| **Downgrade Conditions** | (i) An independent backtest fails to confirm the effect; (ii) a logical flaw is discovered in the derivation; (iii) the single supporting empirical result is shown to be in-sample only. |

### Level D — Experimental Hypothesis

| Attribute | Definition |
| :--- | :--- |
| **Definition** | The idea is a plausible hypothesis with weak or no supporting evidence. It requires significant testing before any claim of validity can be made. |
| **Acceptance Criteria** | (i) A clearly stated, falsifiable hypothesis; (ii) no known contradictory evidence; (iii) the hypothesis is testable against historical data per FEAT-001 §11.9. |
| **Required Supporting Material** | The hypothesis statement; the rationale for why the effect is expected; a defined falsification condition (what result would disprove it). |
| **Required Documentation** | Hypothesis dossier (see §8 template) — minimal; mostly a well-formed question. |
| **Required Validation** | A backtest is the **mandatory next step** before any promotion. No walk-forward, paper trading, or production eligibility is possible at this level. |
| **Allowed Usage** | **Research only.** May be discussed, formalized, and tested. **Never** enters shadow mode. **Never** touches production. |
| **Risk Level** | **High.** The effect is unverified and may not exist. |
| **Promotion Eligibility** | Promotable to **Level C** only after a positive local backtest that meets the future backtesting-governance document's success metrics. |
| **Downgrade Conditions** | (i) A backtest returns a negative result (effect absent or adverse); (ii) the hypothesis is shown to be unfalsifiable; (iii) the hypothesis is shown to violate a FEAT-001 §2 constraint (e.g., requires shorting, or requires live LLM inference). |

### Level E — Speculation

| Attribute | Definition |
| :--- | :--- |
| **Definition** | The idea is pure speculation or opinion, with no supporting evidence and no formalized hypothesis. It should **never** be implemented directly. |
| **Acceptance Criteria** | **None.** Level E is the default assignment for any idea that does not meet Level D acceptance criteria. |
| **Required Supporting Material** | None expected. An idea log entry is the only artefact. |
| **Required Documentation** | A one-paragraph idea log entry capturing the speculation and why it is not yet testable. |
| **Required Validation** | None possible at this stage. |
| **Allowed Usage** | **Brainstorming and discussion only.** Never implemented. Never tested against production data. Never enters any pipeline stage. |
| **Risk Level** | **Not applicable** — the idea is never implemented, so it carries no production risk. The risk is *organizational*: treating speculation as actionable. |
| **Promotion Eligibility** | Promotable to **Level D** once the speculation is formalized into a falsifiable hypothesis with a stated falsification condition. |
| **Downgrade Conditions** | **None.** Level E is the floor. |

### 4.1 Level Summary Matrix

| Level | Evidence Basis | Production-Eligible | Shadow-Eligible | Backtest Required | Risk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | Peer-reviewed + replicated | Yes | Yes | By future governance | Low |
| **B** | Practitioner + multi-implementation | Yes (after shadow) | Yes | Yes (mandatory) | Low–Medium |
| **C** | Logical + limited empirical | No | Yes | Yes (mandatory) | Medium |
| **D** | Hypothesis only | No | No | Yes (next step) | High |
| **E** | None / opinion | No | No | No | N/A |

---

## 5. Evidence Scoring Rubric

To make level assignment **deterministic and reproducible**, evidence is scored on five weighted dimensions, each independently checkable against an artefact. The total score maps to a level via fixed thresholds.

### 5.1 Scoring dimensions

| # | Dimension | Max Points | What is being measured | Artefact required to score > 0 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Academic literature support** | 25 | Peer-reviewed evidence and independent replication | ≥ 1 peer-reviewed citation with DOI/stable URL |
| 2 | **Practitioner / professional adoption** | 25 | Use by professional traders and named systems | ≥ 1 textbook or named practitioner source |
| 3 | **Empirical / statistical evidence** | 25 | Quantitative demonstration of the effect | ≥ 1 empirical study or internal analysis with reported metric |
| 4 | **Independent replication / confirmation** | 15 | Confirmation by parties other than the original proposer | ≥ 1 independent replication or second implementation |
| 5 | **Evidence stability / robustness** | 10 | Performance across regimes, time periods, and out-of-sample | Evidence demonstrated across ≥ 2 distinct market regimes |
| | **Total** | **100** | | |

### 5.2 Per-dimension scoring scale

Each dimension is scored on a fixed 0 / partial / full scale. No subjective "high/medium/low" is permitted at scoring time.

**Dimension 1 — Academic literature support (max 25)**
| Score | Criterion |
| :--- | :--- |
| 0 | No peer-reviewed source |
| 10 | 1 peer-reviewed source, no replication |
| 18 | 2 independent peer-reviewed sources |
| 25 | ≥ 3 independent peer-reviewed sources, ≥ 1 replication |

**Dimension 2 — Practitioner / professional adoption (max 25)**
| Score | Criterion |
| :--- | :--- |
| 0 | No practitioner or textbook source |
| 8 | 1 textbook or practitioner source |
| 17 | ≥ 2 independent practitioner sources |
| 25 | ≥ 3 sources **and** implemented in ≥ 2 named independent systems |

**Dimension 3 — Empirical / statistical evidence (max 25)**
| Score | Criterion |
| :--- | :--- |
| 0 | No empirical result |
| 8 | Internal/in-sample analysis only |
| 17 | ≥ 1 out-of-sample empirical result |
| 25 | Statistically significant effect with reported confidence interval, out-of-sample |

**Dimension 4 — Independent replication / confirmation (max 15)**
| Score | Criterion |
| :--- | :--- |
| 0 | Only the proposer has examined the claim |
| 6 | 1 independent confirmation |
| 15 | ≥ 2 independent confirmations |

**Dimension 5 — Evidence stability / robustness (max 10)**
| Score | Criterion |
| :--- | :--- |
| 0 | Single-regime, single-period evidence only |
| 5 | Evidence spans ≥ 2 market regimes (bull + bear, etc.) |
| 10 | Evidence spans ≥ 2 regimes **and** ≥ 2 distinct out-of-sample time windows |

### 5.3 Level thresholds (deterministic mapping)

| Total Score | Assigned Level |
| :--- | :--- |
| **≥ 85** | **A** |
| **65 – 84** | **B** |
| **40 – 64** | **C** |
| **15 – 39** | **D** |
| **0 – 14** | **E** |

### 5.4 Determinism guarantee

Two independent reviewers, given the same evidence dossier, must arrive at the same dimension scores (each is a countable artefact check) and therefore the same total and the same level. If reviewers disagree on a dimension score, the **lower** score is used (conservative tie-break, mirroring FEAT-004 §4's "when in doubt, be conservative").

---

## 6. Evidence Checklist

Every future feature must satisfy **all** of the following before its Evidence Level is considered valid. A failure on any item blocks level assignment and returns the idea to `Level E (default)`.

- [ ] **C1.** The idea has been submitted using the FEAT-003 §5 Candidate Idea Submission Template.
- [ ] **C2.** Primary `COMP-*` tag and primary `SIT-*` tag are assigned and validated against FEAT-003 Rules 1–4.
- [ ] **C3.** The idea type is declared (one of: `hard-filter`, `soft-score-factor`, `watch-only-signal`, `explanation-only`, `reject-or-defer`).
- [ ] **C4.** An Evidence Level (A–E) has been assigned using the §5 rubric.
- [ ] **C5.** Each scoring dimension's points are backed by a named, retrievable artefact (citation, track record, analysis output).
- [ ] **C6.** A completed Evidence Documentation Template (§8) is attached.
- [ ] **C7.** All acceptance criteria for the assigned level are individually checked off (§4).
- [ ] **C8.** No outstanding uncontested contradictory evidence exists (or it is documented and the level is capped accordingly).
- [ ] **C9.** Re-evaluation triggers (§12) are documented for this idea.
- [ ] **C10.** The deterministic logic check is met: the level can be recomputed by a second reviewer from the dossier alone, with no judgement calls.

---

## 7. Evidence Documentation Template

Every graded idea must carry a completed copy of this template, attached to its FEAT-003 §5 submission. The template is the **only** artefact accepted as evidence; verbal claims do not score.

```markdown
### Evidence Dossier — [Idea Name]

- **Idea Name:** [Brief descriptive title]
- **FEAT-003 Submission Reference:** [Link/anchor to the Candidate Idea Submission]
- **Primary Component Tag:** COMP-[...]
- **Primary Situation Tag:** SIT-[...]
- **Idea Type:** [hard-filter | soft-score-factor | watch-only-signal | explanation-only | reject-or-defer]
- **Known Gap Addressed (FEAT-001 §8):** [#N or "None — new capability"]

#### Assigned Evidence Level: [A | B | C | D | E]

#### Scoring (per §5.2)
- Dimension 1 — Academic literature support: [0–25] — [artefact reference]
- Dimension 2 — Practitioner / professional adoption: [0–25] — [artefact reference]
- Dimension 3 — Empirical / statistical evidence: [0–25] — [artefact reference]
- Dimension 4 — Independent replication: [0–15] — [artefact reference]
- Dimension 5 — Evidence stability: [0–10] — [artefact reference]
- **Total:** [0–100] → **Level [A|B|C|D|E]**

#### Supporting Artefacts
1. [Citation / source / analysis — author, year, venue or location]
2. [...]

#### Acceptance Criteria Check (for assigned level, per §4)
- [ ] Criterion (i): [met / not met] — [evidence]
- [ ] Criterion (ii): [met / not met] — [evidence]
- [ ] ...

#### Contradictory Evidence (if any)
- [Source, summary, and how it was weighed]

#### Re-evaluation Triggers (per §12)
- [List the triggers under which this level will be re-examined]

#### Deterministic Logic Check
- A second reviewer given only this dossier can recompute Level [X]: [Yes/No]
- Reviewer 2 name / date: [...]
```

---

## 8. Evidence Documentation Template — Field Guide

The template in §7 is the *form*. This section is the *guide* — what each field must contain to be valid. Reviewers reject dossiers that do not meet these field requirements.

| Field | Valid content | Invalid content (auto-rejects) |
| :--- | :--- | :--- |
| Supporting Artefacts | Full citations with author, year, venue, DOI/stable URL; or internal analysis filename with date and metric | "See online forums"; "traders say this works"; unattributed claims |
| Academic source | Peer-reviewed journal, conference proceeding, or working paper from a recognized institution | Blog post, social media, vendor marketing, YouTube video |
| Practitioner source | Named textbook, named fund's published methodology, named platform's documented feature | Anonymous testimonials, "a friend who trades" |
| Empirical result | Reported metric (win rate, Sharpe, etc.), sample period, in/out-of-sample split | "Tested well" with no numbers |
| Replication | Named second party, second dataset, or second time window | The proposer's own re-run on the same data |
| Stability | Named regimes (e.g., "tested 2020 bull and 2022 bear") | "Works generally" |

### 8.1 Handling incomplete dossiers

If a dossier is submitted with any field referencing invalid content (right column above), the offending artefact is **stripped**, the dimension is re-scored at 0 for that artefact, and the level is recomputed. The idea is **not** rejected outright — but its level will drop accordingly. This preserves determinism: the level always reflects only valid artefacts.

---

## 9. Evidence Promotion Workflow

This workflow governs **evidence-level promotion only**. It is **not** an implementation lifecycle and **not** a production rollout. It does not replace backtesting, walk-forward validation, paper trading, or production monitoring — those remain the responsibility of future governance documents.

Promotion moves an idea **up the evidence scale** as supporting material accumulates. It never moves an idea into production directly.

### 9.1 Promotion ladder

```
                      ┌─────────────────────────────────────────┐
                      │   EVIDENCE-LEVEL PROMOTION (FEAT-005)   │
                      │   Governs evidence strength ONLY.       │
                      │   Does NOT touch production.            │
                      └─────────────────────────────────────────┘

   Level E  ──►  formalize into falsifiable hypothesis  ──►  Level D
   (Speculation)                                              (Experimental)

   Level D  ──►  positive local backtest (≥1 out-of-sample    ──►  Level C
   (Experimental)   empirical result + logical derivation)        (Logical + partial)

   Level C  ──►  ≥2 independent confirmations OR wider         ──►  Level B
   (Logical)         practitioner adoption                        (Professional)

   Level B  ──►  peer-reviewed academic replication            ──►  Level A
   (Professional)                                                 (Academic)

   Level A  ──►  terminal level (no promotion above A)
   (Academic)
```

### 9.2 Per-transition requirements

| Transition | Required evidence delta | Who must verify |
| :--- | :--- | :--- |
| **E → D** | A written falsifiable hypothesis with a stated falsification condition | Reviewer per §11 |
| **D → C** | A positive local backtest, out-of-sample, plus a logical derivation of the mechanism | Reviewer + backtest result artefact |
| **C → B** | ≥ 2 additional independent confirmations, or documented adoption in ≥ 2 named independent systems | Reviewer + named sources |
| **B → A** | ≥ 1 peer-reviewed academic study replicating the effect | Reviewer + peer-reviewed citation |

### 9.3 What this workflow does NOT do

To remove any ambiguity (per the user's requirement #8):

- It does **not** promote an idea into shadow mode.
- It does **not** promote an idea into production.
- It does **not** replace backtesting, walk-forward validation, paper trading, or production monitoring.
- It does **not** schedule or prioritize implementation.
- It does **not** grade code quality.

Each of those is owned by a separate concern. Evidence promotion only raises the *confidence ceiling* an idea is allowed to occupy.

### 9.4 Promotion record

Every promotion event is logged with: idea name, previous level, new level, the evidence delta that justified it, the verifier, and the date. The record is append-only. Demotions (§4 downgrade conditions, §12 triggers) are logged the same way with the trigger named.

---

## 10. Automatic Rejection Rules

The following conditions cause an idea to be **rejected from evidence grading** and returned to `Level E (default)` automatically. No reviewer discretion applies. These are deterministic.

| # | Rule | Effect |
| :--- | :--- | :--- |
| **AR-1** | No FEAT-003 §5 submission template attached | Cannot be graded; remains Level E |
| **AR-2** | Primary `COMP-*` or `SIT-*` tag missing or invalid (not in FEAT-002 closed sets) | Cannot be graded; remains Level E |
| **AR-3** | Idea requires a new runtime agent or new runtime component | Rejected per FEAT-003 Instruction 8 (non-redesign); remains Level E |
| **AR-4** | Idea requires live LLM inference in the decision path | Rejected per FEAT-001 §2 / §11.10; remains Level E |
| **AR-5** | Idea violates a FEAT-001 §2 non-negotiable constraint (e.g., shorting, non-NIFTY-500 universe, auto-execution) | Rejected; remains Level E |
| **AR-6** | All cited artefacts are in the §8 invalid-content list (blogs, social media, vendor marketing) | Dimensions re-score to 0; total < 15 → Level E |
| **AR-7** | The idea re-raises a known gap (FEAT-001 §8) as a "new discovery" instead of citing it by number | Rejected; rewrite and resubmit citing the gap number |
| **AR-8** | Two reviewers cannot reproduce the same level from the same dossier (determinism failure) | Conservative tie-break applies; if still disputed, level is capped at C until the dossier is repaired |
| **AR-9** | A claim of Level A is made but ≥ 1 acceptance criterion in §4 Level A is unchecked | Level is recomputed at the highest level whose criteria are *all* met |
| **AR-10** | The dossier references a retracted source without flagging it | Source is stripped, dimension re-scored, level recomputed; if the proposer knew of the retraction, the idea is held for review per §12 |

---

## 11. Evidence Review Process

### 11.1 Two-reviewer rule

Every evidence grading requires **two independent reviewers**. Both must reach the same level from the same dossier, unaided by each other. This is the mechanism that makes grading reproducible.

### 11.2 Review procedure

1. **Self-assessment.** The proposer scores the idea using §5 and completes the §7 template.
2. **Reviewer 1.** Independently re-scores all five dimensions from the dossier artefacts only. Records a level.
3. **Reviewer 2.** Independently re-scores all five dimensions. Records a level.
4. **Consensus check.**
   - If both reviewers agree → that level is assigned.
   - If they disagree by one level → the **lower** level is assigned (conservative, per §5.4).
   - If they disagree by more than one level → AR-8 applies; dossier is repaired and re-reviewed.

### 11.3 Reviewer qualifications

A reviewer must not be the proposer of the idea under review. A reviewer need not be a domain expert in the specific technique, because the §5 rubric is artefact-based, not judgement-based. The reviewer's job is to verify that each artefact exists and meets the §8 field guide — not to opine on whether the idea is good.

### 11.4 Review record

Each review records: idea name, proposer, Reviewer 1 + level, Reviewer 2 + level, final level, consensus path taken, date. Append-only.

---

## 12. Evidence Re-evaluation Triggers

An Evidence Level is not permanent. The following triggers require the level to be re-examined and, if warranted, downgraded. Re-evaluation is mandatory; ignoring a trigger is a process violation.

| # | Trigger | Mandatory action | Possible outcome |
| :--- | :--- | :--- | :--- |
| **RT-1** | A new peer-reviewed study contradicts the claim | Re-score Dimension 1 and 4; weigh contradiction per §8 | Downgrade, possibly to E |
| **RT-2** | An independent replication fails to reproduce the effect | Re-score Dimension 4 to 0; recompute | Downgrade by ≥ 1 level |
| **RT-3** | The local backtest (once run, under future governance) returns a negative result | Re-score Dimension 3; cap level at D until resolved | Downgrade to D |
| **RT-4** | Paper trading (once run, under future governance) shows sustained underperformance | Re-score Dimension 5; flag instability | Downgrade by ≥ 1 level |
| **RT-5** | Market structure change (e.g., STT revision, settlement cycle change, new NSE rules) | Re-examine whether cited evidence still applies to the new structure | Downgrade if evidence is now regime-specific to a defunct structure |
| **RT-6** | A cited source is formally retracted | Strip the source per AR-10; recompute | Downgrade |
| **RT-7** | Time-based: 12 months elapsed since last grading with no re-review | Mandatory re-review; reconfirm or adjust | Confirm or downgrade |
| **RT-8** | The idea's mechanism is shown to violate a FEAT-001 §2 constraint not previously caught | Apply AR-5 | Reject to Level E |

### 12.1 Re-evaluation is downgrade-biased

Re-evaluation may confirm the current level or lower it. It does **not** raise the level — raising requires the §9 promotion workflow with a new evidence delta. This asymmetry is intentional: it is conservative and matches FEAT-004 §4's "when in doubt, be conservative" tie-break.

---

## 13. Worked Examples

Each example reuses a real feature from the codebase or a known gap from FEAT-001 §8. Component and situation tags are taken from FEAT-002 §5 / FEAT-003 — the evidence verdict is the only new content. Examples are illustrative, not authoritative gradings.

### Example 1 — Backtest Transaction Costs (Slippage + Fees)
- **One-line idea:** Apply a flat slippage penalty and statutory transaction costs (STT, brokerage, exchange fees) to every backtest fill, addressing FEAT-001 §8 Gaps #13 and #14.
- **Primary Component Tag:** `COMP-BT`
- **Primary Situation Tag:** `SIT-BMR`
- **Idea Type:** `soft-score-factor` (alters backtest P&L)
- **Evidence base:** Extensive peer-reviewed literature on transaction-cost-adjusted returns (e.g., Lo, Mamaysky & Wang on market efficiency with costs; Korajczyk & Sadka on liquidity-adjusted performance); standard treatment in quantitative finance textbooks (e.g., Chan, Narang); implemented in every professional backtesting platform.
- **Dimension scores:** D1 = 25 (≥3 peer-reviewed); D2 = 25 (≥3 sources, ≥2 systems); D3 = 25 (significant out-of-sample effect on reported returns); D4 = 15 (≥2 independent replications); D5 = 10 (cost drag observed across all regimes).
- **Total: 100 → Level A.**
- **Why this is correct:** The claim "transaction costs materially reduce reported backtest returns" is among the most replicated findings in quantitative finance. It satisfies every Level A acceptance criterion.
- **Likely misgrading risk:** Scoring it Level B because the *specific* NIFTY 500 cost structure is not yet modeled locally. *Correction:* Level grades the *claim* (costs matter), which is Level A; the local parameterization is an implementation concern, not an evidence concern.

### Example 2 — Market Regime Overlay (FEAT-004 itself)
- **One-line idea:** Compute a discrete broad market regime from the benchmark index and apply it as a soft score modifier, addressing FEAT-001 §8 Gap #1.
- **Primary Component Tag:** `COMP-REC`
- **Primary Situation Tag:** `SIT-BMR`
- **Idea Type:** `soft-score-factor` with optional `watch-only-signal`
- **Evidence base:** Regime-switching models are well-established academically (Hamilton 1989, Markov-switching literature); trend-following via SMA crossovers is practitioner-standard; however the *specific* four-state discretization (FAV/NEU/CAU/DEF) and the specific score deltas (-3.0, -5.0) are FEAT-004's own design and not independently validated.
- **Dimension scores:** D1 = 18 (2 peer-reviewed — regime models, trend-following); D2 = 17 (≥2 practitioner sources); D3 = 8 (internal design, not yet independently backtested); D4 = 0 (only the proposer); D5 = 5 (literature spans regimes; the specific thresholds do not yet).
- **Total: 48 → Level C.**
- **Why this is correct:** The *concept* is well-supported but the *specific implementation* is a single-party design with no replication. Level C accurately reflects "logically sound, partially validated." This is exactly why FEAT-004 mandates shadow mode before activation — it cannot be Level A on its own design alone.
- **Likely misgrading risk:** Inflating to Level B by citing the regime-switching literature for the *specific* score deltas. *Correction:* The literature supports the *concept*; the deltas are unvalidated design choices and must not borrow the concept's evidence.

### Example 3 — Volatility Squeeze Detection (Bollinger + Keltner)
- **One-line idea:** Detect pre-breakout squeezes where Bollinger Bands contract inside Keltner Channels, addressing FEAT-001 §8 Gap #7.
- **Primary Component Tag:** `COMP-TA`
- **Primary Situation Tag:** `SIT-CSE`
- **Idea Type:** `soft-score-factor`
- **Evidence base:** The Bollinger Band squeeze is a widely-used practitioner technique originating with John Bollinger; documented in multiple trading textbooks and implemented in most charting platforms. Peer-reviewed academic coverage is thinner than for transaction costs.
- **Dimension scores:** D1 = 10 (1 source, no replication); D2 = 25 (≥3 sources, ≥2 systems); D3 = 17 (≥1 out-of-sample practitioner study); D4 = 6 (1 independent confirmation); D5 = 5 (tested across regimes in practitioner work).
- **Total: 63 → Level C.**
- **Why this is correct:** Strong practitioner adoption but limited academic replication places this squarely in Level C territory (close to the B boundary). It would promote to Level B with a second independent empirical confirmation.
- **Likely misgrading risk:** Scoring Level B by counting Bollinger's own book twice (author and platform). *Correction:* Same author's book and platform count as one source, not two. Independent means independent parties.

### Example 4 — News Sentiment Time-Decay
- **One-line idea:** Apply exponential decay to news sentiment so older headlines carry less weight, addressing FEAT-001 §8 Gap #5.
- **Primary Component Tag:** `COMP-NEWS`
- **Primary Situation Tag:** `SIT-GN`
- **Idea Type:** `soft-score-factor`
- **Evidence base:** Time-decay of information value is a sound logical principle (older news is less actionable); there is published empirical work on news sentiment decay in equity markets, but the specific decay half-life for NIFTY 500 headline-only sentiment is not established.
- **Dimension scores:** D1 = 10 (1 source); D2 = 8 (1 textbook-level treatment of decay generally); D3 = 8 (in-sample reasoning only); D4 = 0; D5 = 0.
- **Total: 26 → Level D.**
- **Why this is correct:** Strong logic, weak specific evidence. The decay *concept* is sound but the *parameterization* for this system's headline-only input is an untested hypothesis. Level D correctly mandates a backtest before any promotion.
- **Likely misgrading risk:** Inflating to Level C by citing the general information-decay literature. *Correction:* General decay ≠ headline-sentiment decay for this universe. The claim being graded is specific; the evidence must be too.

### Example 5 — Multi-Timeframe Confirmation
- **One-line idea:** Require a higher-timeframe (weekly) trend alignment before a daily BUY is confirmed, addressing FEAT-001 §8 Gap #10.
- **Primary Component Tag:** `COMP-TA`
- **Primary Situation Tag:** `SIT-CSE`
- **Idea Type:** `hard-filter` or `watch-only-signal`
- **Evidence base:** Multi-timeframe analysis is standard practitioner doctrine (Elder, Murphy, multiple platform methodologies); academic work on multi-scale trend confirmation exists but is less replicated than transaction-cost literature.
- **Dimension scores:** D1 = 10 (1 source); D2 = 25 (≥3 sources, ≥2 systems); D3 = 8 (in-sample practitioner results); D4 = 6 (1 confirmation); D5 = 5.
- **Total: 54 → Level C.**
- **Why this is correct:** Widely practiced but the specific "weekly must align with daily" rule has limited independent quantitative validation. Level C is honest. Promotable to B with one more independent empirical confirmation.
- **Likely misgrading risk:** Scoring Level B because "everyone does it." *Correction:* Popularity is practitioner adoption (Dimension 2), not replication (Dimension 4). They are scored separately.

### Example 6 — Lunar-Phase Entry Timing (deliberate Level E)
- **One-line idea:** Time BUY entries to lunar phases, claiming moon cycles predict NIFTY 500 swings.
- **Primary Component Tag:** `COMP-REC` (hypothetically)
- **Primary Situation Tag:** `SIT-BMR`
- **Idea Type:** `reject-or-defer`
- **Evidence base:** No peer-reviewed support; no practitioner adoption in mainstream systems; no internal analysis. Any cited sources are typically blogs or non-peer-reviewed lunar-cycle sites.
- **Dimension scores:** D1 = 0; D2 = 0; D3 = 0; D4 = 0; D5 = 0.
- **Total: 0 → Level E.**
- **Why this is correct:** Pure speculation with no valid artefacts. Per AR-6 and §4 Level E, it may be discussed but never implemented. It can only leave Level E by being formalized into a falsifiable hypothesis (E → D), at which point a backtest would in all likelihood return it to E.
- **Likely misgrading risk:** A proposer citing a lunar-cycle trading blog. *Correction:* Blogs are invalid content per §8; stripped to 0; remains Level E.

### Example 7 — Adaptive BUY Threshold by Volatility Regime
- **One-line idea:** Raise the BUY composite threshold when India VIX is elevated, instead of the fixed 72.
- **Primary Component Tag:** `COMP-REC`
- **Primary Situation Tag:** `SIT-BMR`
- **Idea Type:** `soft-score-factor`
- **Evidence base:** Volatility-regime-dependent threshold adjustment is logically grounded (high VIX implies wider distributions, so requiring higher conviction is rational); practitioner literature discusses VIX-adjusted position sizing more than VIX-adjusted score thresholds; limited direct replication for the specific threshold rule.
- **Dimension scores:** D1 = 10; D2 = 17; D3 = 8; D4 = 0; D5 = 5.
- **Total: 40 → Level C (lower boundary).**
- **Why this is correct:** Sound logic, partial practitioner grounding, no replication of the *specific* rule. Level C mandates a backtest before any shadow eligibility. The closeness to the D boundary (39) is itself a signal that this idea is evidentially fragile and should be treated cautiously.
- **Likely misgrading risk:** Rounding 40 up to "comfortably C" and rushing to shadow. *Correction:* A score at a level boundary is an explicit caution flag; the conservative tie-break (§5.4) and the shadow-not-permitted-for-D asymmetry should make the reviewer careful.

---

## 14. Brownfield Safety Confirmation

FEAT-005 is a governance document. It touches no runtime code. The following invariants are confirmed.

| Constraint | Status |
| :--- | :--- |
| No existing FEAT-001 through FEAT-004 document is modified | ✅ Confirmed — FEAT-005 consumes them by reference only |
| No new `COMP-*` component tags introduced | ✅ Confirmed — Evidence Level is orthogonal to the tag grammar |
| No new `SIT-*` situation tags introduced | ✅ Confirmed |
| No new runtime agents or runtime components | ✅ Confirmed — FEAT-005 is a process/rulebook, not code |
| No live LLM inference introduced anywhere | ✅ Confirmed — grading is artefact-based and two-reviewer reproducible |
| Deterministic: same dossier → same level | ✅ Confirmed — enforced by §5.4 conservative tie-break and §11 two-reviewer rule |
| Backward compatible with the existing pipeline | ✅ Confirmed — no pipeline stage, threshold, or Gate is altered |
| No known gap (FEAT-001 §8) re-raised as a new discovery | ✅ Confirmed — examples cite gaps by number |
| Rollback / demotion requires no code change | ✅ Confirmed — level is a design-time attribute recorded in the dossier |
| Implementation-independent | ✅ Confirmed — an idea can be fully graded with no production code existing |

---

## 15. Final Recommendation

**Adopt FEAT-005 v1.0 as the canonical evidence classification framework for all future trading recommendation enhancements.**

Application guidance:

1. **Effective immediately**, no future feature may be discussed for implementation without an assigned Evidence Level. An idea without a level defaults to Level E and is treated as speculation.
2. **FEAT-004 (Market Regime Overlay) is retrospectively gradeable** as Level C (Example 2). This is consistent with its own shadow-mode-first mandate — a feature that already knew it needed validation before activation.
3. **The five levels are closed.** No Level F, no Level A+. If an idea exceeds Level A criteria, it remains Level A (terminal).
4. **The promotion workflow (§9) is evidence-only.** It is deliberately separate from — and does not replace — backtesting, walk-forward validation, paper trading, or production rollout. Those remain governed by future documents and by FEAT-004's established shadow→active precedent.
5. **The two-reviewer rule (§11) is non-negotiable.** It is the mechanism that makes evidence grading deterministic and reproducible. Single-reviewer grading is not permitted.
6. **Conservative tie-breaks apply everywhere** (§5.4, §11.2, §12.1). When evidence is ambiguous, the lower level is assigned. This mirrors the OS's foundational conservatism ("when in doubt, be conservative," FEAT-004 §4).

FEAT-005 is the fourth governance layer of the Research Operating System. It does not modify what came before it; it adds one deterministic question — *"how well-proven is this?"* — that every future idea must answer before it may proceed.

---

*End of EVIDENCE_HIERARCHY v1.0 — FEAT-005 Baseline*
