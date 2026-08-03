# RE-001 Trend Continuation Engine

Lab-only recommendation engine. Does **not** own production shortlists.

## Scope

- Evaluate shortlist / full-analysis symbols only
- Stages: `OFF` | `LAB_SHADOW` | `PAPER_LINKED`
- Persist Decision Objects to `recommendation_engine_decisions`
- Fail-open relative to production analysis

## Non-goals

- Replacing production RecommendationService
- Scanner / TA formula changes
- Live broker orders
- Auto-promotion to production shortlist
