# Tasks: Portfolio Configuration Infrastructure

**Input**: Design documents from `/specs/005-portfolio-config/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure
*(No setup tasks needed for this configuration extension).*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented
*(No foundational tasks needed).*

---

## Phase 3: User Story 1 - Configure Portfolio Simulation Parameters (Priority: P1) 🎯 MVP

**Goal**: System administrators or automated systems need to be able to supply portfolio simulation parameters through the centralized configuration infrastructure with strict boundary checks.

**Independent Test**: Initialize the `Settings` instance in Python and assert that the defaults match the specification. Verify overrides and boundaries (validation errors raised on invalid inputs).

### Implementation for User Story 1

- [X] T001 [US1] Extend `Settings` class in `backend/app/config/settings.py` to add `portfolio_simulation_enabled`, `portfolio_max_concurrent_positions`, `portfolio_max_position_pct`, `portfolio_minimum_trade_value`, `portfolio_allow_fractional_shares`, `portfolio_reserve_cash_enabled`, and `portfolio_starting_capital` properties.
- [X] T002 [US1] Add Pydantic field validators and constraint limits to the extended properties in `backend/app/config/settings.py` (e.g. `ge=1`, `gt=0.0`, `le=100.0`, `ge=0.0`, `ge=1000.0`, and validating that `portfolio_allow_fractional_shares` is strictly `False`).

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T003 Run `quickstart.md` validation scenarios to ensure all defaults are active, overrides function, and boundaries are strictly enforced.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: N/A
- **Foundational (Phase 2)**: N/A
- **User Stories (Phase 3+)**: Can start immediately.
- **Polish (Final Phase)**: Depends on User Story 1 completion.

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories.

### Parallel Opportunities

- No parallel opportunities identified as tasks T001 and T002 are sequential modifications to the same file.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3: User Story 1
2. **STOP and VALIDATE**: Test User Story 1 independently using `quickstart.md` validation scenarios.
3. Deploy/demo if ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify validation failure rules behave correctly before completing T002
