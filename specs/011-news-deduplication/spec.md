# Feature Specification: News Deduplication & Research Workflows

**Feature Branch**: `011-news-deduplication`  
**Created**: 2026-07-21  
**Status**: Draft  
**Input**: User description: "Build the first production candidate feature for the Recommendation Engine Enhancement: News Deduplication (FEAT-014) plus the supporting research workflow templates (FEAT-009)."

---

## 1 Feature Summary

This feature addresses the issue of "sentiment inflation" in stock recommendation generation, which occurs when multiple near-duplicate news headlines reporting the same corporate event artificially inflate sentiment scores. To mitigate this without altering the live production recommendation scores, this specification defines:

1. **A Pure News-Article Deduplication Engine**: A low-risk, high-explainability heuristic that filters out near-duplicate articles for a single stock within a 4-hour window by checking word overlaps in titles, prioritizing high-reliability sources, and selecting the earliest article on ties.
2. **An Isolated Shadow Mode Execution Pathway**: A risk-isolated pipeline runner that executes the deduplication logic in the background, logs deduplication decisions to an audit log table, records original vs. kept count statistics in the recommendation metadata (`shadow_outputs`), and ensures that live production sentiment scoring is completely untouched.
3. **Five Reusable Research-Workflow Prompt Templates (FEAT-009)**: Reusable, version-controlled markdown prompts that enforce the project's governance framework for all future candidate strategy ideas.

## Clarifications

### Session 2026-07-21

- Q: Should common English stop words be filtered out before checking the 3-word overlap threshold? → A: Filter out common English stop words before applying the 3-word overlap threshold (Option A).
- Q: Where in the repository should the five new research prompt templates (FEAT-009) be saved? → A: Store the files inside a new subfolder: `AI_PROMPTS/research/` (Option A).
- Q: What should the name of the new SQL table be for logging the deduplicated news articles? → A: Name the table `news_deduplication_audit` (Option A).
- Q: What format/structure should the copy-pasteable prompt template files follow to make sure they are reusable and clear? → A: Markdown templates with standard placeholder variables (e.g., `{{VARIABLE_NAME}}`) and explicit XML-style tags for sections (Option A).

---

## 2 Previous Specification Review

- **Sprint 1 (Baseline & Diagnostics)**: Established database schemas for logging and telemetry. Shadow mode will write to the audit logs using the existing database log persistence structure.
- **FEAT-008 (Research Registry & Lifecycle)**: Defined tables (`research_sessions`, `research_ideas`, `research_critiques`, `research_syntheses`, `research_decisions`, `research_rollout_states`) for capturing research workflow steps. The prompt templates (FEAT-009) must output structured content that can be persisted directly to these tables.
- **FEAT-006 (Research Idea Lifecycle)**: Described the workflow states of an idea from proposal to implementation.
- **COMPONENT_SITUATION_TAXONOMY**: Maps news deduplication to component `COMP-NEWS` and situations `SIT-CSE` (Company-Specific Event), `SIT-GN` (Good News), and `SIT-BN` (Bad News).

---

## 3 Current Architecture Analysis

The existing sentiment scoring pipeline works as follows:
1. `NewsAnalysisAgent` fetches recent news articles for a stock.
2. The articles are passed to a sentiment scoring module to produce a composite sentiment score.
3. This sentiment score is passed to the `RecommendationAgent` to build a final composite recommendation.

### Insertion Point for Shadow Mode
The shadow news-deduplication execution pathway will run alongside the production news pipeline.
- Production News Pipeline: Fetches articles, does NOT filter them, calculates the production sentiment score, and passes it to recommendation generation.
- Shadow Pathway: Fetches the same articles, passes them to the pure deduplication logic, logs the removed duplicates and kept articles, writes telemetry to `shadow_outputs`, and terminates. It operates in complete isolation, ensuring any failure in shadow mode does not disrupt the live pipeline.

---

## 4 User Scenarios & Testing *(mandatory)*

### User Story 1 - Pure News Deduplication (Priority: P1)

As a portfolio manager, I want the news deduplication logic to identify and collapse multiple articles reporting the same event within a short time frame so that I don't see duplicate signals.

**Why this priority**: Essential core heuristic logic.
**Independent Test**: Provide the deduplication function with a list of 5 near-duplicate titles within a 4-hour window and verify that only 1 is kept.

**Acceptance Scenarios**:

1. **Given** a list of recent news articles for a stock, **When** articles are published within 4 hours of each other and share 3 or more title words (case-insensitive), **Then** they are identified as duplicates, and only the highest priority source is kept.
2. **Given** duplicate articles from the same source category (e.g., both Reuters), **When** they are within the 4-hour window, **Then** the earliest article is kept.
3. **Given** a list of 60 recent news articles, **When** passed to the deduplication engine, **Then** the input is capped at the 50 most recent articles before deduplication logic is applied.

---

### User Story 2 - Shadow Mode Isolation & Auditing (Priority: P1)

As a system risk officer, I want the news deduplication to run in shadow mode without altering production sentiment scores or recommendations, while logging all deduplication activity.

**Why this priority**: Zero-risk validation in production environments.
**Independent Test**: Enable shadow mode, verify that production scores are unchanged, and verify that the shadow audit logs and telemetry database records are populated.

**Acceptance Scenarios**:

1. **Given** shadow mode is enabled, **When** a recommendation scan runs, **Then** the live recommendation sentiment scoring is computed using the full, unfiltered article list.
2. **Given** a duplicate news article is removed in shadow mode, **When** the execution completes, **Then** a record is created in the audit table containing the kept ID, the deduplicated ID, a similarity placeholder, and the removal reason.
3. **Given** a recommendation scan finishes, **When** the output is persisted, **Then** the `shadow_outputs` JSONB column contains telemetry mapping the original article count to the kept article count.

---

### User Story 3 - Version-Controlled Governance Prompts (Priority: P2)

As a quantitative researcher, I want standard, version-controlled markdown prompt templates to guide my research sessions so that every new strategy enhancement follows the project's strict quality standards.

**Why this priority**: Enforces governance and consistency for all future candidate ideas.
**Independent Test**: Verify that the five prompt template markdown files are version-controlled and can be copy-pasted directly into a fresh chat session.

**Acceptance Scenarios**:

1. **Given** a new research session, **When** I use the prompt templates sequentially, **Then** they lead me through Context Injection, Research Generation, Adversarial Critique, Synthesis, and Implementation Brief stages.
2. **Given** a prompt template output, **When** generated by an AI, **Then** it produces structured database inputs that match the tables in the FEAT-008 schema.

---

### Edge Cases

- **Special Characters in Titles**: Titles like "AAPL: Earnings Beat!" and "AAPL - Earnings Beat" must be matched correctly even if punctuation differs. Word overlap calculation must strip punctuation before counting.
- **Empty or Single Article Input**: If 0 or 1 articles are provided, the engine must return the input as-is immediately without throwing exceptions.
- **Source Priority Ties on Earliest Timestamp**: If two articles have identical sources and identical timestamps, the system must break the tie deterministically (e.g., sort by alphanumeric ID).
- **Shadow Mode Database Outage**: If writing to the shadow audit log fails, the system must catch the exception, write a warning to the logs, and allow the production recommendation flow to complete successfully.

---

## 5 Requirements *(mandatory)*

### Functional Requirements

#### News Deduplication Engine (FEAT-014)
- **FR-001**: The system MUST accept a list of news articles for a single stock and cap the input at the 50 most recent articles by publication timestamp.
- **FR-002**: The system MUST group articles into 4-hour time windows starting from the earliest article's timestamp.
- **FR-003**: The system MUST detect near-duplicates within each 4-hour window by checking if their titles share 3 or more words (case-insensitive, ignoring punctuation) after excluding common English stop words.
- **FR-004**: The system MUST resolve duplicate groups by keeping only the article from the highest-reliability source according to this hierarchy:
  1. Reuters / Bloomberg (highest reliability)
  2. CNBC / MarketWatch (medium reliability)
  3. All other/unknown sources (lowest reliability)
- **FR-005**: If multiple duplicate articles share the same highest reliability level, the system MUST keep the one with the earliest publication timestamp.
- **FR-006**: The deduplication logic MUST be pure, meaning it returns the filtered list of kept articles and has no side effects (no database updates, no variable mutations outside its scope).

#### Shadow Mode Execution & Auditing
- **FR-007**: The system MUST run the news deduplication logic in complete isolation from the production recommendation pipeline.
- **FR-008**: The system MUST NOT alter the articles used to compute production sentiment scores or recommendations.
- **FR-009**: The system MUST log all removed articles in a dedicated audit log table named `news_deduplication_audit`, recording:
  - `kept_id`: The ID of the article that was kept.
  - `deduplicated_id`: The ID of the article that was removed.
  - `similarity`: A placeholder representing similarity (set to a default value like `1.0` or overlap count).
  - `reason`: A text description explaining the removal (e.g., "Duplicate in 4h window, source priority tie-breaker applied").
- **FR-010**: The system MUST record telemetry in the existing `shadow_outputs` JSONB column of the recommendation record, saving the format: `{"original_news_count": X, "kept_news_count": Y}`.
- **FR-011**: Any exception raised during shadow deduplication or audit logging MUST be caught and logged as a warning, and MUST NOT interrupt the production recommendation pipeline.

#### Research-Workflow Prompts (FEAT-009)
- **FR-012**: The system MUST provide five reusable research-workflow prompt templates as version-controlled markdown files stored inside the `AI_PROMPTS/research/` directory:
  1. `01_context_injection.md`
  2. `02_research_generation.md`
  3. `03_adversarial_critique.md`
  4. `04_synthesis.md`
  5. `05_implementation_brief.md`
- **FR-013**: The prompt templates MUST guide the user to input and format data matching the database schema defined in FEAT-008.
- **FR-014**: The prompt templates MUST be structured as Markdown files using standard placeholder variables (e.g., `{{VARIABLE_NAME}}`) and explicit XML-style tags (e.g., `<input>`, `<expected_output>`) to ensure structural clarity.

### Key Entities

- **News Article**: Represents a single fetched news item. Attributes: `id` (string), `title` (string), `timestamp` (datetime), `source` (string).
- **Deduplication Audit Record**: An entry in the `news_deduplication_audit` table representing a removed duplicate. Attributes: `kept_id` (string), `deduplicated_id` (string), `similarity` (string/float), `reason` (string).
- **Shadow Telemetry**: Metadata saved in the recommendation record under `shadow_outputs` tracking execution counts.
- **Workflow Prompt Template**: Markdown files defining step-by-step instructions for AI research sessions.

---

## 6 Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of news duplicate groups (titles sharing 3+ case-insensitive words in 4 hours) are collapsed to a single article with the highest priority source.
- **SC-002**: Production sentiment scores and recommendations match baseline calculations with 100% precision (zero variance) when shadow mode is running.
- **SC-003**: Deduplication decisions are recorded in the audit database logs within 5 seconds of the shadow run completion.
- **SC-004**: The five prompt templates exist as version-controlled markdown files and are ready to be used.

---

## 7 Assumptions

- **A-001**: Word matching uses simple whitespace and punctuation splitting. Common English stop words (e.g., *the, a, and, of, in, on, for, with, to, is, at*) are filtered out prior to matching. Complex NLP stemming or lemmatization is out of scope for this simple heuristic.
- **A-002**: The 4-hour grouping window starts from the earliest article in the list, then subsequent windows start from the next ungrouped earliest article.
- **A-003**: The database and connection pools are sufficient to handle shadow mode audit logging without performance degradation.
