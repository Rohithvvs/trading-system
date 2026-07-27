# Authoritative Candle Store tests

Canonical automated tests for feature `020-authoritative-candle-store` live under:

```text
backend/tests/test_authoritative_candle_store.py
backend/tests/test_l1_candle_cache.py
backend/tests/test_candle_gap_filler.py
backend/tests/test_candle_store_*.py
backend/tests/integration/test_candle_store_*.py
```

Root `tests/` no longer hosts ACS duplicates (module basename collisions with `backend/tests/`).

```bash
pytest backend/tests/test_authoritative_candle_store.py \
       backend/tests/test_l1_candle_cache.py \
       backend/tests/test_candle_gap_filler.py \
       backend/tests/test_candle_store_feature_flag.py \
       backend/tests/test_candle_store_consistency_audit.py \
       backend/tests/test_candle_store_failure_paths.py \
       backend/tests/test_candle_store_edge_cases.py \
       backend/tests/test_candle_store_consumer_routing.py \
       backend/tests/integration/test_candle_store_*.py -q
```
