from enum import Enum
from pydantic import BaseModel

class CacheState(Enum):
    FRESH_COMPLETE = "FRESH_COMPLETE"
    FRESH_INCOMPLETE = "FRESH_INCOMPLETE"
    STALE_COMPLETE = "STALE_COMPLETE"
    STALE_INCOMPLETE = "STALE_INCOMPLETE"
    CORRUPTED = "CORRUPTED"
    EMPTY = "EMPTY"

class CacheHealthContext(BaseModel):
    symbol: str
    timeframe: str
    cached_rows: int
    required_rows: int
    continuity_gap_count: int
    cache_state: CacheState
    is_valid_for_indicators: bool
