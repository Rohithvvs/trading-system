# Research: Taxonomy Alignment & Historical Backfill

This research document analyzes and resolves the technical decisions for implementing the `situation_tags` column, the non-blocking database migration, and the controlled batch backfill engine.

## Technical Decisions & Resolutions

### Decision 1: Database Representation for Multi-Tagging
- **Resolution**: Use PostgreSQL native `TEXT[]` (Array of Text) column type.
- **Rationale**: 
  - Allows storing multiple tags for a single recommendation without the overhead of a join table.
  - Native Postgres array operations are fast and supported by SQLAlchemy.
  - Using a default empty array `{}` avoids null values and simplifies query handling.
- **SQLAlchemy mapping**:
  ```python
  from sqlalchemy.dialects.postgresql import ARRAY
  from sqlalchemy import Text
  
  situation_tags: Mapped[list[str]] = mapped_column(
      ARRAY(Text), 
      server_default="{}", 
      nullable=False
  )
  ```

### Decision 2: Non-Blocking Database Migration
- **Resolution**: Implement a safe, multi-step Alembic migration.
- **Rationale**:
  - Direct addition of a column with a default on a live table can cause brief locks, but a native `TEXT[]` column with a `server_default` of `'{}{}'` (empty array) is fast in modern PostgreSQL (PostgreSQL 11+ metadata-only default columns do not rewrite the table).
  - Creating a GIN index on a large active table (`analysis_history`) can block writes. To prevent this, the GIN index MUST be created concurrently:
    ```sql
    CREATE INDEX CONCURRENTLY ix_analysis_history_situation_tags ON analysis_history USING gin (situation_tags);
    ```
  - In Alembic, this requires setting `postgresql_using='gin'` and executing the index creation with `commit()` to break the transaction block, since `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.
  - Alembic code snippet:
    ```python
    # For concurrent index creation, we disable transaction block in alembic
    context.configure(compare_type=True, transactional_ddl=False)
    # inside upgrade():
    op.add_column('analysis_history', sa.Column('situation_tags', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False))
    op.execute("COMMIT")  # Close active transaction
    op.create_index('ix_analysis_history_situation_tags', 'analysis_history', ['situation_tags'], unique=False, postgresql_using='gin')
    ```

### Decision 3: Keyset Paging for Batch Backfill
- **Resolution**: Use keyset paging (cursor-based paging) on the primary key `id` of `analysis_history` instead of `OFFSET`/`LIMIT`.
- **Rationale**:
  - `OFFSET` queries require scanning all previous rows, which degrades performance as the offset increases (leads to $O(N)$ query time).
  - Keyset paging filters by `id > last_processed_id` which uses the primary key index directly, guaranteeing stable $O(1)$ query times regardless of dataset size (up to 1,000,000 records).
- **Throttling/Lock Mitigation**:
  - Batches will be kept small (e.g., 1,000 records per batch).
  - A sleep duration (e.g., `await asyncio.sleep(0.1)`) will be introduced between batches to yield control to other database queries and prevent pool starvation.

### Decision 4: Deterministic Tagging Rules
- **Resolution**: Implement a pure Python function that evaluates the context and returns a list of situation tags.
- **Rules Definitions**:
  - `GOOD_NEWS_CATALYST`: Recommendation is `BUY` and news sentiment score is `> 0.6`.
  - `BAD_NEWS_CATALYST`: Recommendation is `SELL` or `WATCH` and news sentiment score is `< 0.4`.
  - `EARNINGS_PLAY`: Queries the `news_articles` table for the symbol within +/- 3 days of the recommendation date, and checks if the title or description contains earnings keywords: `"earnings"`, `"q1"`, `"q2"`, `"q3"`, `"q4"`, `"quarter"`, `"dividend"`, `"results"`, `"profit"`, `"revenue"`.
  - `MARKET_REGIME`: Broad market trend is active (i.e. `market_state` is not null/empty and matches restrictive/extraordinary conditions, e.g. not neutral).
  - `RANGE_BOUND`: Recommendation is not `BUY` and no catalyst tags are matched (fallback tag).
  - `UNKNOWN`: Critical context data (like recommendation action, symbol, or date) is missing.

### Decision 5: Progress Logging & Resumability
- **Resolution**: Use a dedicated schema model `BackfillProgress` to persist state.
- **Attributes**: `job_id`, `last_processed_id`, `status` (RUNNING, PAUSED, COMPLETED, FAILED), `processed_count`, `total_count`.
- **Rationale**: Enables safe resumption from the exact last processed ID and tracks real-time progress for observability.

## Alternatives Considered
1. **Join Table (`analysis_tags`)**: Rejected because it increases database storage footprint, requires multi-table inserts, and slows down retrieval queries due to join overhead.
2. **Comma-Separated String (`TEXT`)**: Rejected because containment queries (`LIKE '%TAG%'`) are slow, prone to false matches, and cannot leverage efficient indexing structures like GIN indexes.
