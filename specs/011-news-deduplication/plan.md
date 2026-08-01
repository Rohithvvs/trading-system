# Implementation Plan: News Deduplication (FEAT-014) & Research Workflows (FEAT-009)

**Branch**: `011-news-deduplication` | **Date**: 2026-07-21 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/011-news-deduplication/spec.md)
**Input**: Feature specification from `specs/011-news-deduplication/spec.md`

## Summary
The goal of this feature is to resolve sentiment inflation in recommendation generation caused by duplicate news headlines, without altering the live production recommendation path. We implement:
1. A pure case-insensitive Title-Word overlap heuristic that filters near-duplicates within a 4-hour window, prioritizing high-reliability sources.
2. A non-blocking, isolated shadow mode runner executed via `ShadowThreadPool` that logs deduplication activity to `article_dedup_log` table and telemetry to `AnalysisHistory.shadow_outputs`.
3. Five reusable research-workflow prompt templates under `AI_PROMPTS/research/` to align AI strategy ideation with FEAT-008 governance database structures.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy (PostgreSQL), Pydantic, asyncio  
**Storage**: PostgreSQL (`article_dedup_log` table and `analysis_history.shadow_outputs` JSONB column)  
**Testing**: pytest  
**Target Platform**: Linux / Windows developer environment  
**Project Type**: Python backend service  
**Performance Goals**: Pure deduplication execution time < 1ms; shadow logging write operations < 50ms, decoupled from the main thread.  
**Constraints**: Zero impact/variance on production sentiment scoring; shadow database errors must degrade gracefully (warn, not raise).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Library-First**: The deduplication logic is written as a pure function in an isolated module `backend/app/services/news_deduplication.py`, completely separate from the orchestrator agent and database services.
- **Principle V: Observability**: Shadow mode log summaries are written to the `app.shadow_executor` logger stream. Mismatches and execution details are logged.
- **Rule of Simplicity**: Simple heuristic word overlap is used instead of complex ML models, embeddings, TF-IDF, or SHAP, keeping the code explainable and fast.

---

## Project Structure

### Documentation (this feature)

```text
specs/011-news-deduplication/
├── plan.md              # This file
├── research.md          # Algorithmic decisions & research notes
├── data-model.md        # Database schema details & telemetry JSON structure
├── quickstart.md        # Pytest run commands and verification scenarios
└── contracts/
    └── news_dedup.json  # Input/Output schema validation definition
```

### Source Code changes

We will create and modify the following files:

```text
backend/
├── app/
│   ├── agents/
│   │   └── news_analysis_agent.py          # Modify NewsAnalysisAgent to trigger shadow deduplication
│   ├── config/
│   │   └── settings.py                     # Verify shadow mode configuration parameters
│   ├── models/
│   │   ├── analysis.py                     # Add shadow_outputs to AnalysisHistory & create ArticleDedupLog table mapping
│   │   └── __init__.py                     # Register ArticleDedupLog table
│   └── services/
│       ├── news_deduplication.py           # Create pure deduplication logic
│       └── shadow_executor.py              # Create ShadowThreadPool & shadow runner task with begin_nested()
└── tests/
    ├── unit/
    │   └── test_news_deduplication.py      # Create unit tests for pure heuristic
    └── integration/
        └── test_news_dedup_shadow.py      # Create integration tests for thread isolation and audit logging
```

---

## Step-by-Step Implementation Flow

### Phase 1: Models & Schema Configuration
1. **Extend `backend/app/models/analysis.py`**:
   - Add column `shadow_outputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)` to `AnalysisHistory` model.
   - Define model `ArticleDedupLog` mapping to the `article_dedup_log` table:
     ```python
     class ArticleDedupLog(Base):
         __tablename__ = "article_dedup_log"
         id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
         symbol: Mapped[str] = mapped_column(String(25), index=True)
         kept_id: Mapped[str] = mapped_column(String(500))
         deduplicated_id: Mapped[str] = mapped_column(String(500))
         kept_title: Mapped[str] = mapped_column(Text)
         deduplicated_title: Mapped[str] = mapped_column(Text)
         similarity: Mapped[float] = mapped_column(Float)
         reason: Mapped[str] = mapped_column(String(250))
         created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
     ```
2. **Register model in `backend/app/models/__init__.py`** and expose it.
3. **Add Alembic Migration**: Create migration version to run `op.add_column("analysis_history", sa.Column("shadow_outputs", postgresql.JSONB))` and `op.create_table("article_dedup_log", ...)` and add a GIN index on `shadow_outputs`.

### Phase 2: Heuristic Implementation
1. **Create `backend/app/services/news_deduplication.py`**:
   - Clean titles by stripping punctuation via regex `r'[^\w\s]'` and lowercasing.
   - Filter out the 24 English stop words: `{"the", "a", "and", "of", "in", "on", "for", "with", "to", "is", "at", "by", "from", "an", "as", "it", "that", "this", "or", "are", "be", "was", "were", "but"}`.
   - Implement `deduplicate_articles(articles: list[ArticleItem]) -> list[ArticleItem]`:
     - Sort articles ascending by `published_at`.
     - Group into 4-hour windows anchoring each window at the earliest ungrouped article.
     - For each window, group articles sharing 3+ clean words.
     - Within each group, keep only the highest priority source: Reuters/Bloomberg (level 3) > CNBC/MarketWatch (level 2) > other (level 1).
     - Break ties using the earliest `published_at` timestamp.
     - Resolve remaining ties using URL sorting.
     - Cap output count per stock at 50 most recent items.

### Phase 3: Shadow Runner and Thread Pool
1. **Create `backend/app/services/shadow_executor.py`**:
   - Define a class-level `ShadowThreadPool`:
     ```python
     class ShadowThreadPool:
         _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ShadowWorker")
         @classmethod
         def submit_task(cls, fn, *args, **kwargs):
             return cls._executor.submit(fn, *args, **kwargs)
     ```
   - Define `execute_shadow_news_dedup(symbol: str, articles: list[ArticleItem]) -> None`:
     - Deep-copy the articles input `copy.deepcopy(articles)` to isolate the shadow path.
     - Execute the pure `deduplicate_articles` function.
     - Open an isolated database session.
     - Within a `session.begin_nested()` context, compare the original list and the deduplicated list.
     - For each removed article, insert an `ArticleDedupLog` record.
     - Update the matching `AnalysisHistory` record's `shadow_outputs` JSONB column with:
       `{"news_dedup": {"original_news_count": X, "kept_news_count": Y, "removed_news_count": Z, "executed_at": "..."}}`
     - Wrap database writes in an exception-safe try/except block. Catch any Database/Connection issues, write warning logs to `app.shadow_executor`, and rollback.

### Phase 4: Pipeline Integration
1. **Inject shadow call in `backend/app/agents/news_analysis_agent.py`**:
   - In `NewsAnalysisAgent.run(symbol)`:
     - After fetching `articles = self.news_service.fetch_recent_news(symbol)`, but before calculating sentiment scoring:
       ```python
       if settings.shadow_mode_enabled:
           from ..services.shadow_executor import ShadowThreadPool, execute_shadow_news_dedup
           ShadowThreadPool.submit_task(execute_shadow_news_dedup, symbol, articles)
       ```
     - Ensure the production path continues using the original `articles` list.

### Phase 5: FEAT-009 Prompt Templates creation
1. Create `AI_PROMPTS/research/` directory.
2. Store the five templates:
   - `01_context_injection.md`: Injects current system context, constraints, and strategy ideas using `{{VARIABLES}}`.
   - `02_research_generation.md`: Prompts LLM to structure a candidate research session.
   - `03_adversarial_critique.md`: Triggers structured critiquing representing potential failure modes.
   - `04_synthesis.md`: Outlines synthesis requirements.
   - `05_implementation_brief.md`: Standardizes the rollout plan brief.
3. Validate templates are copy-pasteable and use clear XML tags (`<expected_output>`, `<validation_rules>`).

---

## Complexity Tracking

*No violations of the Constitution identified.*
