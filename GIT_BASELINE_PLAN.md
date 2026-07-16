# Git Baseline Plan
**Document:** GIT_BASELINE_PLAN.md
**Version:** 1.0
**Date:** 2026-07-12
**Author:** Principal Software Architect & Git Release Manager
**Status:** Plan — requires System Owner approval before execution.
**Objective:** Establish a clean, reproducible, rollback-safe git baseline before Phase-1 implementation of FEAT-008, FEAT-004, FEAT-007.
**Constraint:** No implementation code generated. No specifications rewritten. No ADRs modified. No git commands executed in this document — this is the plan only.

---

## 1. Current Repository Assessment

### 1.1 Branch state
| Item | Value |
| :--- | :--- |
| Active branch | `SAI_CHANDRA` |
| Other local branches | `develop`, `main`, `scanner-debug` |
| Remote tracking | `origin/SAI_CHANDRA`, `origin/develop`, `origin/main`, `origin/scanner-debug` |
| `origin/HEAD` | -> `origin/main` |
| Existing tags | **None** (`git tag -l` returns empty) |
| Last commit on `SAI_CHANDRA` | `0fd99f8 fix(auth): point production SPA at Render API for mobile login` |

### 1.2 Working tree state
| Category | Count | Detail |
| :--- | :--- | :--- |
| Modified tracked files | 12 | 10 source/schema/model files + 2 log files + 1 frontend lockfile |
| Untracked files/dirs | ~38 | Governance docs, feature specs, ADRs, backend services, migrations, tests, scratch dir |

### 1.3 Modified tracked files (12)
| File | Change scope | Commit concern |
| :--- | :--- | :--- |
| `backend/app/agents/backtest_agent.py` | +11 lines | FEAT-008 realism agent wrapper |
| `backend/app/agents/orchestrator_agent.py` | +107 lines | SR-003/SR-004 post-Gate wiring + realism persistence |
| `backend/app/main.py` | +4 lines | Router registration (walk_forward, event_calendar) |
| `backend/app/models/analysis.py` | +30 lines | **Interleaved**: realism metrics + SR-003/SR-004 audit columns |
| `backend/app/schemas/__init__.py` | +4 lines | New schema exports (walk_forward, event_calendar) |
| `backend/app/schemas/analysis.py` | +43 lines | **Interleaved**: BacktestResult realism fields + SR schema additions |
| `backend/app/services/__init__.py` | +4 lines | New service exports (feat004, sector_rs, market_permission, walk_forward, event_calendar) |
| `backend/app/services/backtest_service.py` | +570 lines | FEAT-008 realism engine (two-pass, costs, slippage) |
| `backend/app/services/recommendation_service.py` | +81 lines | FEAT-004 overlay hook + composite wiring |
| `backend/fyersApi.log` | +19 lines | **LOG FILE — should NOT be tracked** |
| `backend/fyersRequests.log` | +130 lines | **LOG FILE — should NOT be tracked** |
| `frontend/package-lock.json` | -512 lines | Frontend dependency lockfile change |

### 1.4 Untracked files (~38)
**Governance & specifications (14):**
- `SHARED_CONTEXT_PACK.md`
- `CLASSIFICATION_RULEBOOK.md`
- `CLASSIFICATION_RULEBOOK_v1.1_FEAT-003_Revised.md`
- `CLASSIFICATION_RULEBOOK_v1.1_FEAT-003_Revised_FROZEN.md`
- `COMPONENT_SITUATION_TAXONOMY.md`
- `FEAT-005_EVIDENCE_HIERARCHY.md`
- `FEAT-006_RESEARCH_IDEA_LIFECYCLE.md`
- `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md`
- `FEAT-004_IMPLEMENTATION_BREAKDOWN.md`
- `FEAT-007_SECTOR_RELATIVE_STRENGTH.md`
- `FEAT-008_REALISTIC_TRADE_EXECUTION_MODEL.md`
- `IMPLEMENTATION_MASTER_PLAN.md`
- `IMPLEMENTATION_PLANNING_REVIEW.md`
- `PHASE0_REPOSITORY_READINESS_REPORT.md`

**Architecture Decision Records (5, in `docs/adr/`):**
- `ADR-001_backtest_execution_model.md`
- `ADR-002_market_regime_consolidation.md`
- `ADR-003_sector_relative_strength_formula.md`
- `EVIDENCE_REPORT_SR_formula_comparison.md`
- `README.md`

**Backend migrations (5, in `backend/alembic/versions/`):**
- `add_backtest_realism_metrics.py` (FEAT-008)
- `add_sector_rs_cols.py` (SR-003 / FEAT-007)
- `add_market_regime_cols.py` (SR-004 / FEAT-004)
- `add_event_calendar_tables.py`
- `add_walk_forward_tables.py`

**Backend models (2):**
- `backend/app/models/event_calendar.py`
- `backend/app/models/walk_forward.py`

**Backend routers (2, in `backend/app/routers/`):**
- `event_calendar.py`
- `walk_forward.py`

**Backend services (5):**
- `backend/app/services/feat004_regime_overlay.py` (FEAT-004 — 741 lines)
- `backend/app/services/sector_rs_service.py` (SR-003 — FEAT-007 reference)
- `backend/app/services/market_permission_service.py` (SR-004)
- `backend/app/services/event_calendar_service.py`
- `backend/app/services/walk_forward_service.py`

**Backend config (1):**
- `backend/app/config/sector_mappings.json` (FEAT-004/007 — 80 symbols, 10 sectors)

**Backend tests (6):**
- `backend/app/tests/test_backtest_realism.py`
- `backend/app/tests/test_event_calendar.py`
- `backend/app/tests/test_feat004_regime_overlay.py`
- `backend/app/tests/test_market_permission.py`
- `backend/app/tests/test_sector_rs_overlay.py`
- `backend/app/tests/test_walk_forward.py`

**Operational artifact (1):**
- `feat004_monitoring_checklist.csv`

**Scratch / investigation (3, in `scratch/`):**
- `inspect_db.py` (scratch script — 350 bytes)
- `sr_formula_observations.csv` (1.3 MB — **ADR-003 evidence data, 10,827 rows**)
- `sr_formula_index_history.csv` (188 KB — **ADR-003 evidence data, 1,223 rows**)

### 1.5 Key risks in the current state
1. **No tags exist** — there is no reproducible reference point for rollback.
2. **Log files are tracked** — `backend/fyersApi.log` and `backend/fyersRequests.log` were committed in prior commits (`f5afe5e`, `07d92dd`, `c52e737`) despite `.gitignore` matching `*.log`. They will pollute every diff and commit until untracked.
3. **Interleaved changes** in `models/analysis.py`, `schemas/analysis.py`, `services/__init__.py`, `schemas/__init__.py` span multiple feature concerns (FEAT-008 realism + SR-003/SR-004 + walk-forward + event-calendar). Clean per-feature commit splitting would require `git add -p` and carries risk of partial staging errors.
4. **ADR-003 evidence data lives in `scratch/`** — the `EVIDENCE_REPORT_SR_formula_comparison.md` and `ADR-003` both reference `scratch/sr_formula_observations.csv` as the reproducibility artifact. If `scratch/` is gitignored or omitted, ADR-003's evidence chain is broken in the repository.
5. **Active branch `SAI_CHANDRA` is a personal-looking branch name** — the baseline should land on a shared, stable branch (`develop` or `main`) to be the authoritative reference.

---

## 2. Files That Should Be Committed Together

### Group A — Governance & specification documents
All governance docs, feature specs, and the Phase-0 readiness report form one coherent governance layer. They have no code dependencies and should be committed as a single atomic governance commit.

**Files (15):**
- `SHARED_CONTEXT_PACK.md`
- `CLASSIFICATION_RULEBOOK.md`
- `CLASSIFICATION_RULEBOOK_v1.1_FEAT-003_Revised.md`
- `CLASSIFICATION_RULEBOOK_v1.1_FEAT-003_Revised_FROZEN.md`
- `COMPONENT_SITUATION_TAXONOMY.md`
- `FEAT-005_EVIDENCE_HIERARCHY.md`
- `FEAT-006_RESEARCH_IDEA_LIFECYCLE.md`
- `FEAT-004_MARKET_REGIME_OVERLAY_SPEC.md`
- `FEAT-004_IMPLEMENTATION_BREAKDOWN.md`
- `FEAT-007_SECTOR_RELATIVE_STRENGTH.md`
- `FEAT-008_REALISTIC_TRADE_EXECUTION_MODEL.md`
- `IMPLEMENTATION_MASTER_PLAN.md`
- `IMPLEMENTATION_PLANNING_REVIEW.md`
- `PHASE0_REPOSITORY_READINESS_REPORT.md`
- `feat004_monitoring_checklist.csv`

### Group B — Architecture Decision Records + evidence
All three ADRs, the ADR README index, and the ADR-003 evidence report plus its backing data. The evidence CSVs must be moved out of `scratch/` into `docs/adr/evidence/` before committing so the ADR references remain valid and `scratch/` can stay untracked.

**Files (7 after move):**
- `docs/adr/README.md`
- `docs/adr/ADR-001_backtest_execution_model.md`
- `docs/adr/ADR-002_market_regime_consolidation.md`
- `docs/adr/ADR-003_sector_relative_strength_formula.md`
- `docs/adr/EVIDENCE_REPORT_SR_formula_comparison.md`
- `docs/adr/evidence/sr_formula_observations.csv` *(moved from `scratch/`)*
- `docs/adr/evidence/sr_formula_index_history.csv` *(moved from `scratch/`)*

> **Pre-commit action:** `git mv scratch/sr_formula_observations.csv docs/adr/evidence/` and same for the index history CSV. Then update the three references in `EVIDENCE_REPORT_SR_formula_comparison.md` and the one reference in `ADR-003` from `scratch/...` to `evidence/...`. This is a path-correction, not a content rewrite — it preserves the ADR's decision and the evidence chain.

### Group C — FEAT-008 backtest realism engine (substrate)
The realism math, its schema, its migration, and its tests form one cohesive code delta.

**Files (6):**
- `backend/app/services/backtest_service.py` (modified, +570 lines)
- `backend/app/agents/backtest_agent.py` (modified, +11 lines)
- `backend/app/schemas/analysis.py` (modified — **partial**: only the BacktestResult realism fields)
- `backend/app/models/analysis.py` (modified — **partial**: only the realism metric columns)
- `backend/alembic/versions/add_backtest_realism_metrics.py` (new)
- `backend/app/tests/test_backtest_realism.py` (new)

> **Interleave note:** `schemas/analysis.py` and `models/analysis.py` contain changes for both FEAT-008 realism AND SR-003/SR-004 columns. If strict per-feature commits are required, use `git add -p` to stage only the realism hunks. If the System Owner accepts grouping C+D+E together (recommended — see Section 5), stage these files whole.

### Group D — SR-003 sector RS + SR-004 market permission (live overlays)
The live post-Gate overlay services, their orchestrator wiring, their migration, and their tests.

**Files (7):**
- `backend/app/services/sector_rs_service.py` (new — SR-003, FEAT-007 reference)
- `backend/app/services/market_permission_service.py` (new — SR-004)
- `backend/app/agents/orchestrator_agent.py` (modified — SR-003/SR-004 post-Gate wiring)
- `backend/app/models/analysis.py` (modified — **partial**: SR-003/SR-004 audit columns)
- `backend/alembic/versions/add_sector_rs_cols.py` (new)
- `backend/alembic/versions/add_market_regime_cols.py` (new)
- `backend/app/tests/test_sector_rs_overlay.py` (new)
- `backend/app/tests/test_market_permission.py` (new)

### Group E — FEAT-004 regime overlay module (complete but not yet wired live)
The FEAT-004 overlay module, its hook in the recommendation service, the sector mapping config, and its tests.

**Files (4):**
- `backend/app/services/feat004_regime_overlay.py` (new — 741 lines)
- `backend/app/services/recommendation_service.py` (modified — FEAT-004 hook + composite wiring)
- `backend/app/config/sector_mappings.json` (new)
- `backend/app/tests/test_feat004_regime_overlay.py` (new — 535 lines)

### Group F — Walk-forward + event-calendar features
These are independent of FEAT-004/007/008 but are part of the uncommitted working tree and must be captured in the baseline.

**Files (9):**
- `backend/app/services/walk_forward_service.py` (new)
- `backend/app/services/event_calendar_service.py` (new)
- `backend/app/models/walk_forward.py` (new)
- `backend/app/models/event_calendar.py` (new)
- `backend/app/routers/walk_forward.py` (new)
- `backend/app/routers/event_calendar.py` (new)
- `backend/app/main.py` (modified — router registration)
- `backend/alembic/versions/add_walk_forward_tables.py` (new)
- `backend/alembic/versions/add_event_calendar_tables.py` (new)
- `backend/app/tests/test_walk_forward.py` (new)
- `backend/app/tests/test_event_calendar.py` (new)

### Group G — Shared index/export files
The `__init__.py` export additions that span all new services/schemas. These are tiny (+4 lines each) and cross-cutting.

**Files (3):**
- `backend/app/services/__init__.py` (modified — service exports)
- `backend/app/schemas/__init__.py` (modified — schema exports)
- *(also `models/analysis.py` and `schemas/analysis.py` but those are covered in C/D)*

### Group H — Frontend lockfile
**Files (1):**
- `frontend/package-lock.json` (modified — -512 lines)

### Group I — Log file untracking (chore)
**Files (2, removed from tracking only):**
- `backend/fyersApi.log` (`git rm --cached`)
- `backend/fyersRequests.log` (`git rm --cached`)

The `.gitignore` already matches `*.log`, so after `git rm --cached` the files will stay on disk but stop being tracked. This prevents future log churn in diffs.

---

## 3. Files That Should NOT Be Committed

| File/Dir | Reason | Disposition |
| :--- | :--- | :--- |
| `backend/fyersApi.log` | Log file; `.gitignore` matches `*.log`; already tracked — untrack via `git rm --cached` | Untrack (Group I) |
| `backend/fyersRequests.log` | Same as above | Untrack (Group I) |
| `scratch/inspect_db.py` | Scratch investigation script; not a production artifact; not referenced by any ADR or spec | Leave untracked; add `scratch/` to `.gitignore` |
| `scratch/` (directory) | After evidence CSVs are moved to `docs/adr/evidence/`, the remaining content is scratch only | Add `scratch/` to `.gitignore` |
| `backend/app/routers/__pycache__/` | Python bytecode cache; `.gitignore` already matches `__pycache__/` | Already ignored — do not commit |
| `.env` | Contains secrets; `.gitignore` matches | Already ignored |
| `venv/`, `node_modules/` | Dependencies; `.gitignore` matches | Already ignored |
| `backend/server_state.json` | Runtime state; `.gitignore` matches | Already ignored |

> **Additional `.gitignore` entry to add:** Append `scratch/` to `.gitignore` as part of the baseline chore commit. This is a one-line gitignore addition, not a source-code change.

---

## 4. Single Commit vs Multiple Commits

### Recommendation: **Multiple commits (9 commits).**

### Rationale
| Factor | Single commit | Multiple commits |
| :--- | :--- | :--- |
| Reproducibility | One hash captures everything | Each layer is independently reproducible |
| Rollback granularity | All-or-nothing | Can revert one layer (e.g., walk-forward) without touching FEAT-008 |
| Bisect utility | Useless — one commit | Meaningful `git bisect` across layers |
| Audit trail | "Phase-0 baseline" — opaque | Each commit documents its concern |
| Risk of partial staging | None | Low — groups are cleanly separable except 2 interleaved files |
| Effort | Minimal | Moderate (~30 min staging) |

The only complication is the **interleaved changes** in `models/analysis.py` and `schemas/analysis.py` (realism fields + SR columns in the same file). Two options:

- **Option 1 (strict separation):** Use `git add -p` to stage only the realism hunks for Group C, then the SR hunks for Group D. Higher precision, higher risk of staging error.
- **Option 2 (pragmatic — RECOMMENDED):** Merge Groups C + D + E + G into a single "backend overlay & realism layer" commit, staging the interleaved files whole. Lower risk, still logically coherent (all are the feature layer the Phase-0 report audits).

**Recommended commit count under Option 2: 7 commits** (governance, ADRs, backend feature layer, walk-forward/event-calendar, frontend, log-untrack chore, gitignore chore).

**Recommended commit count under Option 1: 9 commits** (the groups as listed in Section 5).

The System Owner should choose. This plan defaults to **Option 2 (7 commits)** in the sequencing below.

---

## 5. Recommended Commit Grouping

**Ordered for logical dependency (each builds on the previous):**

| # | Commit | Group(s) | Files | Depends on |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Chore: untrack log files + gitignore scratch | I + gitignore | 2 untracked logs + `.gitignore` | None |
| 2 | Governance: add FEAT-001..008 governance & spec documents | A | 15 docs | #1 |
| 3 | Architecture: add ADR-001/002/003 + evidence | B | 7 files (incl. moved CSVs) | #2 |
| 4 | Backend: FEAT-008 realism + SR-003/SR-004 overlays + FEAT-004 module | C+D+E+G | 15 files | #3 |
| 5 | Backend: walk-forward + event-calendar features | F | 11 files | #4 |
| 6 | Frontend: update dependency lockfile | H | 1 file | #1 |
| 7 | Tag: phase-0-baseline (annotated tag on commit #5 or #6) | — | — | #6 |

> Commits #4 and #5 could be swapped (#5 before #4) without harm — walk-forward/event-calendar are independent of the FEAT overlay layer. The order above groups the FEAT-audit-relevant code first for review clarity.

---

## 6. Branch Strategy

### Recommendation
```
  main (stable, production)
   |
   +-- develop (integration branch)
         |
         +-- phase-0-baseline (working branch for this baseline)
```

### Steps
1. **Create a dedicated working branch from the current `SAI_CHANDRA` HEAD:**
   ```
   git checkout SAI_CHANDRA
   git checkout -b phase-0-baseline
   ```
   This preserves `SAI_CHANDRA` as-is and isolates the baseline work.

2. **Execute the 6 commits (Section 9) on `phase-0-baseline`.**

3. **Merge `phase-0-baseline` into `develop`:**
   ```
   git checkout develop
   git merge --no-ff phase-0-baseline
   ```
   `--no-ff` preserves the baseline as a merge commit for auditability.

4. **Merge `develop` into `main` (or open a PR):**
   ```
   git checkout main
   git merge --no-ff develop
   ```
   Or prefer the PR route: `gh pr create --base main --head develop --title "Phase-0 baseline: governance, ADRs, feature layer"`.

5. **Tag the merge commit on `main`** (Section 7).

6. **Delete the temporary working branch:**
   ```
   git branch -d phase-0-baseline
   ```

### Why not commit directly on `SAI_CHANDRA`?
`SAI_CHANDRA` is a personal-named branch that also exists on `origin`. Committing the baseline there would mix the baseline with prior auth/frontend work and make the tag's ancestry harder to audit. A dedicated `phase-0-baseline` branch keeps the history clean.

### Why not commit directly on `main`?
Direct commits to `main` bypass review. The PR route (or at minimum the `develop` -> `main` merge) preserves an audit trail.

---

## 7. Tag Strategy

### Recommendation: **One annotated tag.**

```
git tag -a phase-0-baseline -m "<message>" <merge-commit-on-main>
```

### Tag naming
- **`phase-0-baseline`** — descriptive, matches the phase naming in `IMPLEMENTATION_PLANNING_REVIEW.md`.
- Annotated (`-a`) not lightweight — annotated tags store the tagger, date, and message, which is essential for an audit gate.
- Do NOT use a semver tag (e.g., `v1.0.0`) yet — no implementation code has been written; this is a pre-implementation baseline, not a release.

### Future tags (for reference, not created now)
| Tag | When | On |
| :--- | :--- | :--- |
| `phase-1-feat008-complete` | After FEAT-008 substrate finalized + shadow-ready | `main` |
| `phase-2-feat004-complete` | After FEAT-004 wired + shadow-ready | `main` |
| `phase-3-feat007-complete` | After FEAT-007 implemented + shadow-ready | `main` |
| `v1.0.0` | After all three features activated in production | `main` |

---

## 8. Rollback Strategy

### 8.1 Rollback to the baseline
If Phase-1 implementation must be abandoned:
```
git reset --hard phase-0-baseline
```
This restores the repository to the exact baseline state — all governance, ADRs, and the feature layer as committed, with no Phase-1 changes.

### 8.1 Rollback a single commit (if multi-commit)
Because the baseline is split into logical commits, a single layer can be reverted without disturbing the others:
```
git revert <commit-hash>
```
For example, if the walk-forward feature (commit #5) is found to be broken, `git revert <#5>` removes it while preserving the governance, ADRs, and FEAT overlay layer.

### 8.2 Rollback guarantees
| Property | Guarantee |
| :--- | :--- |
| Reproducibility | The `phase-0-baseline` tag points to a specific commit hash; `git reset --hard phase-0-baseline` always returns to the exact same tree. |
| Auditability | Annotated tag + `--no-ff` merge commits preserve the full chain of commits for review. |
| Granularity | Multi-commit grouping allows `git revert` of one layer without touching others. |
| Log file safety | After commit #1, log files are untracked; rollback does not restore them to tracking. |
| Evidence integrity | ADR-003 evidence CSVs are committed under `docs/adr/evidence/`; rollback restores them. |

### 8.3 Pre-baseline checkpoint (recommended safety net)
Before starting the commit sequence, create a temporary checkpoint tag on the current dirty state so nothing is lost if staging goes wrong:
```
git tag -a pre-baseline-checkpoint -m "Checkpoint before Phase-0 baseline staging"
```
Delete it after the baseline is confirmed:
```
git tag -d pre-baseline-checkpoint
```

---

## 9. Recommended Commit Messages

All messages follow the conventional-commit style observed in the repo's recent history (`fix(auth): ...`, `feat(scanner): ...`).

### Commit #1 — Chore: untrack logs + gitignore
```
chore(repo): untrack log files and add scratch/ to gitignore

Remove backend/fyersApi.log and backend/fyersRequests.log from git
tracking (already matched by .gitignore *.log pattern). Add scratch/
to .gitignore for investigation artifacts.

Phase-0 baseline preparation — GIT_BASELINE_PLAN.md step 1.
```
**Files staged:** `backend/fyersApi.log` (rm --cached), `backend/fyersRequests.log` (rm --cached), `.gitignore`

### Commit #2 — Governance & specs
```
docs(governance): add FEAT-001..008 governance, specs, and Phase-0 report

Add the completed governance and specification layer:
- FEAT-001 Shared Context Pack
- FEAT-002 Component x Situation Taxonomy
- FEAT-003 Classification Rulebook (v1, v1.1 Revised, v1.1 Frozen)
- FEAT-005 Evidence Hierarchy
- FEAT-006 Research Idea Lifecycle
- FEAT-004 Market Regime Overlay spec + implementation breakdown
- FEAT-007 Sector Relative Strength spec
- FEAT-008 Realistic Trade Execution Model spec
- Implementation Master Plan + Planning Review
- Phase-0 Repository Readiness Report
- feat004 monitoring checklist

No code changes. All governance documents are complete and frozen.
```
**Files staged:** 15 docs (Group A)

### Commit #3 — ADRs + evidence
```
docs(adr): add ADR-001/002/003 and ADR-003 evidence report

Add the three accepted Architecture Decision Records:
- ADR-001 Backtest Execution Model (Option B — brand, switch, verify)
- ADR-002 Market Regime Consolidation (Option C — merge with separated
  responsibilities)
- ADR-003 Sector Relative Strength Formula (Option C-Revised —
  difference formula canonical)

Include the Phase-0 evidence report and its backing data
(sr_formula_observations.csv, 10,827 rows; sr_formula_index_history.csv,
1,223 rows) under docs/adr/evidence/ for ADR-003 reproducibility.

ADRs are accepted as of 2026-07-11/12 per System Owner governance.
```
**Files staged:** 7 files (Group B, after CSV move + path-reference fix)

### Commit #4 — Backend feature layer
```
feat(backend): add FEAT-008 realism engine, SR-003/SR-004 overlays,
and FEAT-004 regime overlay module

FEAT-008 (COMP-BT): two-pass backtest engine with causal next-bar-open
fills, full Indian NSE cost stack (brokerage/STT/exchange/SEBI/stamp/
GST/DP), symmetric slippage, position sizing, retro-fee logic. Adds
gross_* realism metrics to BacktestResult schema and analysis_history.
Migration: add_backtest_realism_metrics.

SR-003 (sector RS, FEAT-007 reference): SectorRelativeStrengthService
with difference formula (sector_roc20 - bm_roc20), binary
WEAK/STRENGTH classification, post-Gate downgrade. Migration:
add_sector_rs_cols.

SR-004 (market permission): MarketPermissionService with NIFTY50
EMA50 + VIX + breadth, 4-state FAVORABLE/CAUTIOUS/HIGHRISK/DEFENSIVE,
post-Gate new_entry_allowed gate. Migration: add_market_regime_cols.

FEAT-004 (COMP-REC, module complete — not yet wired live):
feat004_regime_overlay.py with 7 helpers (resolve_benchmark_ohlcv,
compute_benchmark_indicators, classify_market_regime, apply_regime_
score_modifier, compute_sector_strength, build_feat004_log_payload,
apply_feat004_regime_overlay). 5-state regime classifier, score deltas
(-3/-5/+2), FAVORABLE cap, SHADOW/ACTIVE staging, full log schema,
safe-fallback. Hook added in recommendation_service.py but caller
passes disabled config — overlay produces zero production effect until
wired. Sector mapping config: sector_mappings.json (80 symbols, 10
sectors).

Tests: test_backtest_realism.py (11), test_feat004_regime_overlay.py
(20), test_sector_rs_overlay.py, test_market_permission.py.

Note: FEAT-004 module is complete but DEAD per ADR-002 Section 2.2.
Wiring + feat004 config section are Phase-2 prerequisites
(PHASE0_REPOSITORY_READINESS_REPORT.md Section 3).
```
**Files staged:** 15 files (Groups C + D + E + G)

### Commit #5 — Walk-forward + event-calendar
```
feat(backend): add walk-forward evaluation and event calendar features

Walk-forward backtest evaluation service with veto history
persistence. NSE/BSE event calendar service with coverage tracking
and ingestion-run audit. New routers: /api/walk-forward, /api/events.
Migrations: add_walk_forward_tables, add_event_calendar_tables.
Tests: test_walk_forward, test_event_calendar.

Independent of FEAT-004/007/008 but captured in the Phase-0 baseline
as part of the uncommitted working tree.
```
**Files staged:** 11 files (Group F)

### Commit #6 — Frontend lockfile
```
chore(frontend): update dependency lockfile

Sync frontend/package-lock.json with current dependency set.
```
**Files staged:** `frontend/package-lock.json`

---

## 10. Recommended Git Tags

| Tag | Type | Target | When | Message |
| :--- | :--- | :--- | :--- | :--- |
| `pre-baseline-checkpoint` | annotated | current `SAI_CHANDRA` HEAD (dirty) | Before staging — temporary safety net | "Checkpoint before Phase-0 baseline staging — delete after baseline confirmed" |
| `phase-0-baseline` | **annotated** | final commit of the baseline sequence on `main` (or `develop` if PR route) | After all 6 commits + merge | See below |

### `phase-0-baseline` tag message
```
Phase-0 Repository Baseline — 2026-07-12

Governance: FEAT-001..008 complete (SHARED_CONTEXT_PACK, CLASSIFICATION
RULEBOOK v1.1 Frozen, COMPONENT_SITUATION_TAXONOMY, EVIDENCE HIERARCHY,
RESEARCH LIFECYCLE, FEAT-004/007/008 specs + breakdown).

Architecture: ADR-001 (Option B), ADR-002 (Option C), ADR-003
(Option C-Revised) — all accepted.

Backend: FEAT-008 realism engine (live, ~85%), SR-003 sector RS
(reference impl, difference formula), SR-004 market permission (live),
FEAT-004 regime overlay module (complete, not wired), walk-forward +
event-calendar features.

Planning: IMPLEMENTATION_MASTER_PLAN, IMPLEMENTATION_PLANNING_REVIEW,
PHASE0_REPOSITORY_READINESS_REPORT, GIT_BASELINE_PLAN.

This tag is the implementation gate. Phase-1 (FEAT-008 substrate
finalization per ADR-001 Option B) begins from this commit.

Go/No-Go: See PHASE0_REPOSITORY_READINESS_REPORT.md Section 11.
```

---

## 11. Go / No-Go Recommendation

### **GO** for executing the Git Baseline Plan.

The repository state is well-understood, the file groupings are cleanly separable (with one pragmatic merge of the interleaved overlay layer), and the rollback path is safe (annotated tag + multi-commit + pre-baseline checkpoint).

### Conditions
1. The plan must be executed **in the order specified** (commits #1 through #6, then tag).
2. The **pre-baseline checkpoint tag** must be created first as a safety net.
3. The **ADR-003 evidence CSVs must be moved** from `scratch/` to `docs/adr/evidence/` and their path references in `EVIDENCE_REPORT_SR_formula_comparison.md` and `ADR-003` updated **before** commit #3. This is a path correction, not a content rewrite.
4. After the baseline is tagged, the **Phase-0 readiness report's NO-GO** (Section 11 of `PHASE0_REPOSITORY_READINESS_REPORT.md`) still governs whether Phase-1 *implementation* can begin. This Git baseline removes **blocker B1** (uncommitted feature layer) but does **not** remove blockers B2 (ADR-003 vs FEAT-007 spec conflict) or B3 (ADR acceptance status reconciliation). Those remain System Owner decisions.

### Execution checklist
| # | Action | Command (reference — do not execute from this doc) |
| :--- | :--- | :--- |
| 0 | Safety net | `git tag -a pre-baseline-checkpoint -m "Checkpoint before Phase-0 baseline staging"` |
| 1 | Create working branch | `git checkout -b phase-0-baseline` |
| 2 | Move evidence CSVs | `mkdir docs/adr/evidence; git mv scratch/sr_formula_observations.csv docs/adr/evidence/; git mv scratch/sr_formula_index_history.csv docs/adr/evidence/` |
| 3 | Fix path references | Update 3 references in `EVIDENCE_REPORT_SR_formula_comparison.md` + 1 in `ADR-003` from `scratch/` to `evidence/` |
| 4 | Add `scratch/` to `.gitignore` | Append `scratch/` to `.gitignore` |
| 5 | Commit #1 (chore) | `git rm --cached backend/fyersApi.log backend/fyersRequests.log; git add .gitignore; git commit` |
| 6 | Commit #2 (governance) | `git add <15 docs>; git commit` |
| 7 | Commit #3 (ADRs) | `git add docs/adr/; git commit` |
| 8 | Commit #4 (backend feature layer) | `git add <15 backend files>; git commit` |
| 9 | Commit #5 (walk-forward + event-calendar) | `git add <11 backend files>; git commit` |
| 10 | Commit #6 (frontend) | `git add frontend/package-lock.json; git commit` |
| 11 | Merge to develop | `git checkout develop; git merge --no-ff phase-0-baseline` |
| 12 | Merge to main (or PR) | `git checkout main; git merge --no-ff develop` *(or `gh pr create`)* |
| 13 | Tag | `git tag -a phase-0-baseline -m "<Section 10 message>" <merge-commit>` |
| 14 | Push | `git push origin main develop --tags` |
| 15 | Clean up | `git tag -d pre-baseline-checkpoint; git branch -d phase-0-baseline` |
| 16 | Verify | `git log --oneline phase-0-baseline -7` confirms 6 commits; `git status` clean; `git show phase-0-baseline --stat` confirms baseline tree |

---

*End of GIT_BASELINE_PLAN v1.0*
