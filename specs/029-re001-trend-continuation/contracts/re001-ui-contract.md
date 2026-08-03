# Contract: RE-001 Lab UI Surfaces

**Feature**: `029-re001-trend-continuation`  
**Status**: Planning contract  
**Visibility**: Admin + Trader when lab feature permission / UI flag enabled

---

## Surfaces

### S1 — Symbol / analysis detail: RE-001 section (required MVP)

**When shown**: Lab permission on AND a RE-001 decision exists for the viewed symbol/context.

**Must display**:
- Label that this is **Lab / RE-001** (not production)
- RecommendationState (BUY / WATCH / REJECT)
- Confidence
- Primary strategy (family + name) when present
- At least one evidence/rationale item
- Validation / reject reason when REJECT (especially `missing_market_context`)
- Production comparison (production action vs RE-001) when both exist

**Must not**:
- Replace production score/action as the primary scanner decision
- Appear when permission off

---

### S2 — Compact Recommendation Lab comparison view (required MVP)

**Entry**: Feature-gated nav item or scanner tab (product choice in tasks).

**Must display**:
- Scan identity / timestamp
- Table or list of shortlisted symbols with production state vs RE-001 state
- Mismatch indicator
- Link/navigation to symbol detail for explainability

**Performance UX**: Operator can complete a scan-level review in under 2 minutes (SC-004).

**Must not**:
- Be required to use retail scanner workflows (SC-008)
- Present as full multi-engine product console (engines marketplace, etc.)

---

### S3 — Retail scanner dashboard (unchanged)

- BUY / WATCH summary cards remain production-sourced.
- Optional subtle badge that lab data exists is allowed if it does not change counts.

---

### S4 — Paper desk provenance (required for paper path)

- When order/prefill originates from RE-001, show engine provenance (RE-001 + version).
- Fill/lifecycle UI unchanged.

---

## Feature permission

| Key (logical) | Roles when active |
| ------------- | ----------------- |
| `recommendation_lab` | Admin, Trader |

Default: inactive until enabled in controlled environments.

---

## Accessibility / clarity

- Lab surfaces use clear “Lab” / “Experimental” labeling to reduce confusion risk.
- Empty states: “RE-001 disabled” vs “No lab decisions for this scan” distinguishable.

---

## Non-goals

- Full multi-engine Lab product page
- Admin-only MVP (rejected in clarify)
- Forced lab gate on retail scanner
