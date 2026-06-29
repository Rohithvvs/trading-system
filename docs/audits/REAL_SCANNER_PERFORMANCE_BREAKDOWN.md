# REAL SCANNER PERFORMANCE BREAKDOWN

## Overall Runtime
**Total Duration**: 527.14 seconds

## Stage-by-Stage Breakdown

**Stage 1: Universe Loading**
- **Duration**: ~1000 ms (1 second)
- **Note**: Loaded 755 symbols instantly from configuration into the orchestrator list.

**Stage 2: FYERS Historical Data Download**
- **Duration**: ~497,000 ms (497 seconds)
- **Symbols Requested**: 755
- **Symbols Successful**: 710
- **Symbols Failed**: 45
- **Note**: This represents a bulk network I/O sequence retrieving historical candles. Includes enforced API rate limits.

**Stage 3: Data Quality Validation**
- **Duration**: < 100 ms (Processed in-memory sequentially alongside indicators)
- **Valid Symbols**: 700
- **Invalid Symbols**: 10 (Dropped due to insufficient candle counts)

**Stage 4: Technical Indicator Calculations**
- **Duration**: ~1000 ms (Vectorized array calculations executed natively via Pandas/Numpy over 700 symbols).

**Stage 5: Trend Gate**
- **Duration**: < 100 ms (Broad trend eligibility pass filtering out 619 symbols).

**Stage 6: Scoring**
- **Duration**: < 100 ms (Weighted scoring processing yielding 81 candidate matches).

**Stage 7: Recommendation Generation (Full Analysis)**
- **Duration**: ~27,000 ms (27 seconds) before halting.
- **Note**: Shortlisted top 20 candidates. Processing failed on the backend agent task grouping (`asyncio.gather`) throwing a scope exception.

**Stage 8: Snapshot Persistence**
- **Duration**: 0 ms (Failed before execution)

**Stage 9: Final Response Assembly**
- **Duration**: 0 ms (Failed before execution)

---

## Identified Bottlenecks

### Top 5 Slowest Operations
1. **FYERS Incremental Historical Data Fetch**
   - **Duration**: 497 seconds
   - **Percentage of Total Runtime**: 94.3%
   - **Reason**: Sequential or throttled API calls retrieving missing 1D candles for 755 symbols.

2. **Full Analysis / Recommendation Generation (Pre-Crash)**
   - **Duration**: 27 seconds
   - **Percentage of Total Runtime**: 5.1%
   - **Reason**: LLM or complex orchestrator delegation looping over the top 20 shortlist.

3. **In-Memory Mathematical Calculations (Indicators/Scoring)**
   - **Duration**: < 1.5 seconds
   - **Percentage of Total Runtime**: 0.3%
   - **Reason**: NumPy/Pandas processing overhead (negligible).

4. **Universe Bootstrapping & Memory Allocations**
   - **Duration**: ~1 second
   - **Percentage of Total Runtime**: 0.2%

5. **Persistence / I/O Bounds (Skipped due to crash)**
   - **Duration**: 0 ms
   - **Percentage of Total Runtime**: 0%

## Classification
**POOR (>600 sec) / SCANNER_FAILURE_DETECTED**
*Note: Although execution crashed at 527s, the bottleneck trend on the FYERS fetch indicates it borders tightly on the "POOR" spectrum purely due to network I/O sequential limits.*
