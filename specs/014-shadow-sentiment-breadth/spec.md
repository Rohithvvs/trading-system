# Feature Specification: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Feature Branch**: `014-shadow-sentiment-breadth`  
**Created**: 2026-07-22  
**Status**: Draft  
**Input**: User description: "Build two independent candidate features that will run simultaneously in Shadow Mode: Sentiment Time-Decay and Market Breadth. These are the next features after the successful promotion of News Deduplication."

---

## 1 Feature Overview

Following the successful promotion of News Deduplication, this feature introduces two new independent candidate features into the Shadow Mode execution engine: **Sentiment Time-Decay (FEAT-018)** and **Market Breadth (FEAT-016)**.

Both candidate features run strictly in parallel in Shadow Mode during live stock scanning, collecting telemetry without altering live production recommendations or scoring.

### Candidate Feature 1: Sentiment Time-Decay (FEAT-018)
- Evaluates recent news articles for a stock by applying an exponential time-decay based on article age.
- Fresh news carries full weight, older news carries progressively reduced weight, and news older than 72 hours is completely zeroed out.
- Produces full diagnostic transparency including original raw sentiment, decayed score, article age, and applied multiplier.
- Runs exclusively in Shadow Mode with zero impact on production sentiment scores.

### Candidate Feature 2: Market Breadth (FEAT-016)
- Assesses overall market health by evaluating the percentage of stocks across the monitored universe trading above their 200-day moving average.
- Translates the market breadth percentage into a soft market regime contribution score ranging from strongly positive to strongly negative, categorized into clear market regime labels (strong, favorable, neutral, weak, very weak).
- Enforces universe size safety checks to prevent unreliable calculations when data coverage is insufficient.
- Runs exclusively in Shadow Mode contributing zero points to live production scoring.

### Parallel Shadow Execution Architecture
- Both features execute concurrently on every scan using the existing Shadow infrastructure.
- Shadow outputs are recorded in isolated namespaces within `shadow_outputs` so neither feature overwrites or interferes with the other.
- Complete fault isolation is guaranteed: a failure or exception in one shadow feature will not crash or affect the other shadow feature or the live production recommendation path.

---

## 2 User Scenarios & Testing *(mandatory)*

### User Story 1 - Shadow Sentiment Time-Decay Evaluation (Priority: P1)

As a quantitative analyst, I want news article sentiment scores to decay exponentially based on article age so that recent news exerts greater influence than stale news without affecting live production recommendations.

**Why this priority**: Core candidate feature logic required to prevent outdated news from inflating or deflating sentiment evaluations.

**Independent Test**: Provide the sentiment time-decay function with news articles of varying publication timestamps (e.g., 2 hours old, 24 hours old, 80 hours old) and verify that decayed scores reflect age-weighted decay, articles >72 hours are zeroed out, and output contains full diagnostic metadata.

**Acceptance Scenarios**:

1. **Given** a set of news articles with raw sentiment scores published within 72 hours, **When** sentiment time-decay is evaluated, **Then** each article receives a decayed sentiment score strictly less than or equal to its raw score based on its age, alongside its calculated age and decay multiplier.
2. **Given** news articles published more than 72 hours ago, **When** sentiment time-decay is evaluated, **Then** those articles are assigned a decayed sentiment score of zero.
3. **Given** a live scan execution, **When** sentiment time-decay runs in Shadow Mode, **Then** its diagnostic output is stored under its dedicated `sentiment_decay` entry in `shadow_outputs`, while live production sentiment remains unmodified.

---

### User Story 2 - Shadow Market Breadth Assessment (Priority: P1)

As a risk manager, I want to evaluate the market-wide participation percentage (stocks above 200-day moving average) so that system recommendations account for broader market regime health.

**Why this priority**: Essential macro regime signal to contextualize stock-level recommendations during broad market rallies versus widespread market weakness.

**Independent Test**: Supply a universe of stock prices and their 200-day moving averages, verify correct breadth percentage calculation, map to appropriate regime labels (strong, favorable, neutral, weak, very weak), and confirm score contribution formatting in Shadow Mode.

**Acceptance Scenarios**:

1. **Given** a universe of stock price data with 200-day moving averages, **When** market breadth is evaluated, **Then** the system calculates the percentage of stocks above their 200-day moving average and assigns a soft regime score contribution and corresponding regime label (strong, favorable, neutral, weak, very weak).
2. **Given** a stock universe size below the minimum required threshold, **When** market breadth is evaluated, **Then** the system marks the result as unreliable/invalid and returns a neutral default without throwing an unhandled error.
3. **Given** a live scan execution, **When** market breadth runs in Shadow Mode, **Then** its output is stored under its dedicated `market_breadth` entry in `shadow_outputs` and contributes zero points to live production scoring.

---

### User Story 3 - Fault-Isolated Parallel Shadow Execution (Priority: P2)

As a system operator, I want both candidate shadow features to run concurrently and independently on every live scan so that a failure in one candidate feature does not impact the other or disrupt production.

**Why this priority**: Guarantees system resilience, operational stability, and uncorrupted shadow data collection.

**Independent Test**: Simulate an unhandled exception or crash in one shadow feature during a live scan, verify that the other shadow feature completes successfully, `shadow_outputs` persists valid results for the surviving feature, and production recommendations are delivered without error.

**Acceptance Scenarios**:

1. **Given** a live scan execution, **When** both shadow features run concurrently, **Then** both `sentiment_decay` and `market_breadth` results are stored in `shadow_outputs` without overwriting each other.
2. **Given** a simulated runtime failure in the market breadth calculation, **When** a live scan occurs, **Then** the sentiment decay shadow feature finishes successfully, its output is logged to `shadow_outputs`, and live production scoring executes normally without error.
3. **Given** historical scan logs across different market conditions, **When** analyzed alongside situation tags, **Then** analysts can independently inspect and compare the behavior of both shadow features across situation tags for future A/B attribution analysis.

---

### Edge Cases

- **Missing Publication Timestamps**: How does Sentiment Time-Decay handle articles without a valid timestamp? It defaults to treating the article as maximum age (>72 hours) with zero weight to prevent unverified stale news from corrupting scores.
- **Insufficient Universe Data**: How does Market Breadth handle scenarios where 200-day moving averages are unavailable for a significant portion of the universe? It flags the breadth metric as invalid due to insufficient coverage and logs a neutral contribution.
- **Empty News Feed**: How does Sentiment Time-Decay handle a stock scan with zero news articles? It safely returns an empty article result set and a neutral score without failing.
- **Concurrent Write Contention**: How does the system handle concurrent persistence of shadow outputs? Writes to `shadow_outputs` use independent keys (`sentiment_decay` and `market_breadth`) within the shadow payload dictionary.

---

## 3 Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a pure function for Sentiment Time-Decay (FEAT-018) that takes news articles with raw sentiment scores and publication timestamps and applies an exponential time-decay calculation.
- **FR-002**: Sentiment Time-Decay MUST completely zero out sentiment scores for any article with a publication timestamp older than 72 hours relative to the scan timestamp.
- **FR-003**: Sentiment Time-Decay MUST return comprehensive diagnostic telemetry for each evaluated article, including original raw score, decayed score, calculated age in hours, and applied decay multiplier.
- **FR-004**: System MUST provide a pure function for Market Breadth (FEAT-016) that calculates the percentage of stocks in the monitored universe trading above their 200-day moving average.
- **FR-005**: Market Breadth MUST convert the calculated percentage into a soft regime contribution score ranging from strongly positive to strongly negative and map it to one of five regime labels: `strong`, `favorable`, `neutral`, `weak`, or `very weak`.
- **FR-006**: Market Breadth MUST validate universe size and data completeness, returning an invalid/neutral indicator when available stock data falls below the required threshold.
- **FR-007**: System MUST execute Sentiment Time-Decay and Market Breadth concurrently in Shadow Mode during every live scan.
- **FR-008**: System MUST store outputs for both features independently in `shadow_outputs` under distinct keys (`sentiment_decay` and `market_breadth`) without key collisions or data loss.
- **FR-009**: System MUST enforce strict fault isolation such that an exception or failure in either shadow feature is caught, logged, and isolated without causing the other shadow feature or production scoring path to fail.
- **FR-010**: Candidate shadow features MUST NOT modify, alter, or contribute to live production sentiment scores or live recommendation points.
- **FR-011**: System MUST record situation tags (from Sprint 6) alongside shadow outputs to enable post-hoc analysis across market conditions.

---

### Key Entities

- **SentimentDecayOutput**: Represents the evaluation result of Sentiment Time-Decay for a stock scan, containing the aggregate decayed score, raw score, and per-article breakdown (article ID/title, raw score, decayed score, age hours, multiplier).
- **MarketBreadthOutput**: Represents the evaluation result of Market Breadth for a universe scan, containing total universe size, valid stock count, stocks above 200-day MA count, breadth percentage, soft regime score contribution, regime label, and validity flag.
- **ShadowOutputEntry**: Represents the structured payload persisted into `shadow_outputs` for a scan session, containing independent sub-objects for `sentiment_decay`, `market_breadth`, and existing shadow features (such as `news_deduplication`).

---

## 4 Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of live scans execute both candidate shadow features concurrently without adding measurable latency to the production recommendation path.
- **SC-002**: 100% of shadow scan records in `shadow_outputs` contain independent, complete data structures for both `sentiment_decay` and `market_breadth`.
- **SC-003**: In 100% of fault injection tests (deliberately crashing one shadow feature), the surviving shadow feature finishes successfully and live production recommendations remain 100% unaffected.
- **SC-004**: Sentiment Time-Decay correctly zeroes out 100% of articles older than 72 hours across all test and live validation scenarios.
- **SC-005**: Analysts can extract and correlate shadow outputs with situation tags to perform A/B attribution analysis across at least 5 distinct market situation categories.

---

## 5 Assumptions

- **Existing Shadow Infrastructure**: The Shadow Mode infrastructure established in Sprint 1 and refined in Sprint 6 is available and supports adding arbitrary key-value entries to `shadow_outputs`.
- **200-Day Moving Average Availability**: Price history data required to compute 200-day moving averages for universe stocks is available via the core market data provider.
- **News Article Timestamps**: News articles fetched by the news analysis pipeline contain standard publication timestamps.
- **Situation Tag Availability**: Situation tagging implemented in Sprint 6 attaches situation metadata to scan execution context.
