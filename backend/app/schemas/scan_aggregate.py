from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScanCandidateDTO(BaseModel):
    """Represents an individual symbol candidate match identified during in-memory analysis."""
    symbol: str
    strategy_name: str
    signal_type: str  # "BUY", "SELL", "NEUTRAL"
    score: float = 0.0
    timeframe: str = "15m"
    close_price: float = 0.0
    volume: int = 0
    indicator_values: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScanAggregateResult(BaseModel):
    """Represents the complete aggregated outcome of a market scan execution before persistence."""
    scan_id: str
    symbol_universe: str = "NIFTY500"
    execution_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    candidates: List[ScanCandidateDTO] = Field(default_factory=list)
    total_scanned: int = 0
    total_candidates: int = 0
    execution_duration_ms: float = 0.0
    save_history: bool = False
    status: str = "SUCCESS"  # "SUCCESS", "TIMEOUT", "FAILED"


@dataclass
class SingleWriteResult:
    """Status object returned by single final write transaction execution."""
    success: bool
    latest_rows_upserted: int = 0
    history_rows_inserted: int = 0
    transaction_duration_ms: float = 0.0
    error_message: Optional[str] = None
