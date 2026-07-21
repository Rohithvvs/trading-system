# Research: News Deduplication & Governance Workflows

This document establishes the technical decisions, algorithmic design, and architectural mitigations for Sprint 4 (News Deduplication FEAT-014 and Research Workflow Prompt Templates FEAT-009).

## 1. Heuristic String Similarity & Stop Word Filtering

### Decision
Use a case-insensitive word-token intersection heuristic that strips common punctuation, filters out a static list of 24 English stop words, and counts exact word overlaps in article titles.
- **Stop Words List**: `{"the", "a", "and", "of", "in", "on", "for", "with", "to", "is", "at", "by", "from", "an", "as", "it", "that", "this", "or", "are", "be", "was", "were", "but"}`
- **Punctuation Regex**: `r'[^\w\s]'` (replace with space to prevent joining tokens like `AAPL-Earnings` to `AAPLEarnings`).
- **Threshold**: 3 or more common words.

### Rationale
- Satisfies the strict constraint against ML models, embeddings, TF-IDF, or external libraries like SpaCy.
- Simple, deterministic, and highly explainable.
- Fast execution speed (< 1ms per comparison), well within runtime latency budgets.

### Alternatives Considered
- **Levenshtein Distance / Levenshtein Ratio**: Rejected because edit distance is highly sensitive to string length variations and sentence structure, leading to false negatives for re-ordered duplicate headlines (e.g., "Earnings Beat: AAPL Up 5%" vs "AAPL Up 5% After Earnings Beat").
- **Jaccard Similarity Coefficient**: Rejected because long headlines containing many descriptive words might fall below a percentage threshold despite sharing core duplicate noun phrases. An absolute word-overlap count is more robust for short headlines.

---

## 2. 4-Hour Time Window Grouping Algorithm

### Decision
Articles are sorted ascending by publication timestamp (`published_at`). The algorithm iterates through the list, forming a 4-hour window starting from the earliest ungrouped article. Any article falling within `[window_start, window_start + 4 hours)` is evaluated for duplication within that window context.
Once a window's articles are processed, the next window starts at the publication timestamp of the next ungrouped earliest article in the list.

```python
def group_by_time_windows(articles: list[ArticleItem]) -> list[list[ArticleItem]]:
    sorted_articles = sorted(articles, key=lambda x: x.published_at)
    windows = []
    current_window = []
    
    for art in sorted_articles:
        if not current_window:
            current_window.append(art)
            continue
        
        window_start = current_window[0].published_at
        if art.published_at - window_start < timedelta(hours=4):
            current_window.append(art)
        else:
            windows.append(current_window)
            current_window = [art]
            
    if current_window:
        windows.append(current_window)
    return windows
```

### Rationale
- Simplifies windowing by anchoring the start of each window on actual data points rather than arbitrary wall-clock hours, reducing empty windows.
- Guarantees O(N log N) sorting overhead and O(N) grouping overhead, which easily fits within performance budgets for N <= 50.

---

## 3. Dedicated Background Thread Pool & Database Thread Safety

### Decision
Use the existing dedicated `ShadowThreadPool` (max_workers=4) to offload the shadow execution.
To guarantee database thread safety:
- Never share the active SQLAlchemy `AsyncSession` of the main request context.
- Inside the background worker, instantiate a new thread-local database session using the synchronous `SessionLocal` class.
- Wrap all writes in `session.begin_nested()` (SAVEPOINT) or a sub-transaction block.
- In case of a database crash, catch the exception, perform a rollback on the thread session, and log a warning without propagating the exception to the parent thread or event loop.

### Rationale
- Python's standard `asyncio` loop can be blocked if deep copying or string matching is executed on large collections.
- Thread-bound database connections prevent crossing session boundaries, eliminating session contamination or transaction lock leakage.

---

## 4. Prompt Template Organization

### Decision
Store the five markdown templates inside the `AI_PROMPTS/research/` folder.
Templates will enforce structural serialization requirements:
- Use standard placeholder variables: `{{VARIABLE_NAME}}`.
- Embody strict XML tags (`<input>`, `<expected_output>`, etc.) for downstream LLM parsing.
- Directly map output fields to schema attributes in FEAT-008.

### Rationale
- Consistent with Sprint 2/3 patterns.
- Clear separation of AI prompt templates from system source code.
