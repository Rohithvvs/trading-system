import logging

logger = logging.getLogger("live_observability")

class LiveObservability:
    """
    Exposes hooks for monitoring Area 5 Telemetry Metrics.
    Actual Prometheus integration would wrap these hooks.
    """

    @classmethod
    def record_stale_executing(cls, count: int) -> None:
        """Records gauge for stale EXECUTING orders."""
        logger.info(f"METRIC [stale_executing_count]: {count}")

    @classmethod
    def record_stale_reconciling(cls, count: int) -> None:
        """Records gauge for stale RECONCILING orders."""
        logger.info(f"METRIC [stale_reconciling_count]: {count}")

    @classmethod
    def record_margin_mismatch(cls, mismatch_amount: float) -> None:
        """Fires when available + reserved + invested != starting_balance."""
        if mismatch_amount != 0:
            logger.critical(f"METRIC ALARM [margin_mismatch_alert]: Detected discrepancy of {mismatch_amount}")

    @classmethod
    def record_broker_timeout(cls) -> None:
        """Increments broker timeout rate counter."""
        logger.warning("METRIC [broker_timeout_rate]: +1")

    @classmethod
    def record_trade_replay(cls, broker_trade_id: str) -> None:
        """Increments trade replay / duplicate event counter."""
        logger.warning(f"METRIC [broker_trade_replay_rate]: +1 for trade {broker_trade_id}")
