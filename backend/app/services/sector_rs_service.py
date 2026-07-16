import json
import pandas as pd
import pytz
from datetime import datetime, date
from pathlib import Path
from ta.trend import EMAIndicator
from ..utils.symbol import canonical_symbol, fyers_symbol
from ..schemas import FinalRecommendation, SectorOverlayResult, AnalysisMode
from .market_data_service import MarketDataService
from ..utils import get_logger

logger = get_logger("app.sector_rs")

class SectorRelativeStrengthService:
    def __init__(self) -> None:
        self.mapping = {}
        mapping_path = Path(__file__).resolve().parent.parent / "config" / "sector_mappings.json"
        if mapping_path.exists():
            try:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    self.mapping = json.load(f)
                logger.info("Loaded %d sector symbol mappings from %s", len(self.mapping), mapping_path)
            except Exception as e:
                logger.error("Failed to load sector mappings: %s", e)
        else:
            logger.warning("Sector mapping file not found at %s", mapping_path)

    def _to_ist_trading_date(self, val) -> date:
        """
        Normalize datetime representations (strings, Timestamps, naive/aware datetimes)
        into a timezone-naive calendar date representing the trading day in India (Asia/Kolkata).
        
        - Timezone-aware values are converted to Asia/Kolkata before extraction.
        - Timezone-naive values are assumed to already be in local market time (Asia/Kolkata).
        """
        if val is None:
            return None

        # Convert string to Timestamp if needed
        if isinstance(val, str):
            val = pd.to_datetime(val)

        has_tz = False
        if hasattr(val, "tzinfo") and val.tzinfo is not None:
            has_tz = True
        elif hasattr(val, "tz") and val.tz is not None:
            has_tz = True

        if has_tz:
            tz_kolkata = pytz.timezone("Asia/Kolkata")
            if hasattr(val, "tz_convert"):
                val_ist = val.tz_convert(tz_kolkata)
            else:
                val_ist = val.astimezone(tz_kolkata)
            normalized_date = val_ist.date()
        else:
            if hasattr(val, "date"):
                normalized_date = val.date()
            else:
                normalized_date = pd.to_datetime(val).date()

        logger.debug("Normalized timestamp %s to India trading date %s", val, normalized_date)
        return normalized_date

    async def evaluate_sector_overlay(
        self,
        symbol: str,
        scan_date: datetime,
        original_recommendation: FinalRecommendation
    ) -> SectorOverlayResult:
        canon_sym = canonical_symbol(symbol)
        sector_symbol = self.mapping.get(canon_sym)

        # Initialize result
        result = SectorOverlayResult(
            mapped_sector=sector_symbol,
            original_action=original_recommendation.action,
            challenger_action=original_recommendation.action,
            downgrade_triggered=False
        )

        if not sector_symbol:
            result.sector_filter_status = "UNMAPPED"
            result.feat007_abstained_reason = "no_sector_mapping"
            return result

        md_service = MarketDataService()

        # Load sector index candles (resolution "1D")
        async def load_candles_for_index(sym: str) -> pd.DataFrame:
            canonical = canonical_symbol(sym)
            df = await md_service.load_full_history(canonical, "1D")
            if df.empty:
                fyers = fyers_symbol(canonical, is_index=True)
                df = await md_service.load_full_history(fyers, "1D")
            return df

        try:
            sector_df = await load_candles_for_index(sector_symbol)
            nifty_df = await load_candles_for_index("NIFTY50-INDEX")

            if sector_df.empty or nifty_df.empty:
                logger.warning(
                    "Sector relative strength overlay aborted: Empty candles for sector=%s or NIFTY50. "
                    "Sector empty=%s, NIFTY empty=%s",
                    sector_symbol, sector_df.empty, nifty_df.empty
                )
                result.sector_filter_status = "INSUFFICIENT_HISTORY"
                result.feat007_abstained_reason = "sector_index_unavailable"
                return result

            # Sort indices chronologically
            sector_df = sector_df.sort_index()
            nifty_df = nifty_df.sort_index()

            # Ensure we have enough data before running technical indicators (EMA20 requires warmup)
            if len(sector_df) < 20:
                logger.warning("Sector %s has insufficient history for indicators (%d rows)", sector_symbol, len(sector_df))
                result.sector_filter_status = "INSUFFICIENT_HISTORY"
                result.feat007_abstained_reason = "insufficient_sector_history"
                return result

            # Calculate EMA20 on full sorted sector closes to avoid warmup bias
            sector_df["ema20"] = EMAIndicator(close=sector_df["close"], window=20).ema_indicator()

            # Map index/timestamp values to India trading date objects
            sector_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in sector_df.index]
            nifty_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in nifty_df.index]

            # Merge sector and NIFTY data using their daily trading dates
            merged = pd.merge(
                sector_df[["trading_date", "close", "ema20"]],
                nifty_df[["trading_date", "close"]],
                on="trading_date",
                suffixes=("_sector", "_nifty")
            )
            merged = merged.sort_values("trading_date")

            # Resolve intended India trading date for the scan cutoff
            scan_trading_date = self._to_ist_trading_date(scan_date)

            # Filter data strictly up to the scan trading date (anti-look-ahead boundary rule)
            merged_filtered = merged[merged["trading_date"] <= scan_trading_date]

            if len(merged_filtered) < 21:
                logger.warning(
                    "Insufficient aligned history for sector=%s after timezone-aligned merge up to trading_date=%s. "
                    "Aligned rows=%d (Required=21)",
                    sector_symbol, scan_trading_date, len(merged_filtered)
                )
                result.sector_filter_status = "INSUFFICIENT_HISTORY"
                result.feat007_abstained_reason = "insufficient_sector_history"
                return result

            # Latest aligned row
            sector_close_t = float(merged_filtered["close_sector"].iloc[-1])
            sector_ema20_t = float(merged_filtered["ema20"].iloc[-1])
            sector_close_t_minus_20 = float(merged_filtered["close_sector"].iloc[-21])

            nifty50_close_t = float(merged_filtered["close_nifty"].iloc[-1])
            nifty50_close_t_minus_20 = float(merged_filtered["close_nifty"].iloc[-21])

            if (pd.isna(sector_close_t) or pd.isna(sector_ema20_t) or pd.isna(sector_close_t_minus_20) or
                pd.isna(nifty50_close_t) or pd.isna(nifty50_close_t_minus_20)):
                logger.warning("Warmup indicators contain NaN values for sector=%s at trading_date=%s", sector_symbol, scan_trading_date)
                result.sector_filter_status = "INSUFFICIENT_HISTORY"
                result.feat007_abstained_reason = "sector_rs_computation_failed"
                return result

            # Formulas
            roc20_sector = ((sector_close_t / sector_close_t_minus_20) - 1) * 100
            roc20_nifty50 = ((nifty50_close_t / nifty50_close_t_minus_20) - 1) * 100
            sector_rs_20 = roc20_sector - roc20_nifty50

            # Populate metrics
            result.sector_close = round(sector_close_t, 2)
            result.sector_ema20 = round(sector_ema20_t, 2)
            result.sector_roc20 = round(roc20_sector, 2)
            result.nifty50_roc20 = round(roc20_nifty50, 2)
            result.sector_rs_20 = round(sector_rs_20, 2)

            # Evaluate Weakness
            is_downtrend = sector_close_t < sector_ema20_t
            is_underperforming = sector_rs_20 < 0

            if is_downtrend and is_underperforming:
                result.sector_filter_status = "WEAK"
                result.downgrade_triggered = True
                result.downgrade_reason = f"Sector {sector_symbol} is weak (close {result.sector_close} < EMA20 {result.sector_ema20}) and underperforming Nifty (RS: {result.sector_rs_20:.2f}%)"
            else:
                result.sector_filter_status = "STRENGTH"

        except Exception as e:
            logger.error("Error evaluating sector overlay: %s", e, exc_info=True)
            result.sector_filter_status = "INSUFFICIENT_HISTORY"
            result.feat007_abstained_reason = "sector_rs_computation_failed"

        return result
