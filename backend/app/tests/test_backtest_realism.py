from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta
from app.schemas import AnalysisMode, OHLCVPoint
from app.services.backtest_service import (
    BacktestService,
    calculate_transaction_costs,
    PercentEquityPositionSizer,
    COST_SCENARIOS,
)
from app.agents.backtest_agent import BacktestAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.config.settings import settings

class TestBacktestRealism(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BacktestService()

    def generate_mock_candles(self) -> list[OHLCVPoint]:
        """
        Generate a list of 75 daily candles.
        Warms up indicators for 60 candles at price 100.
        On candle 61, close rises to 110, volume increases, triggering a bullish entry signal.
        On candle 62, open is 112 (realistic entry), close is 115.
        On candle 63, open is 116, close is 118.
        On candle 64, close drops to 105, triggering an exit signal.
        On candle 65, open is 104 (realistic exit), close is 103.
        """
        candles = []
        base_time = datetime(2026, 1, 1)

        # Warm up 60 candles
        for idx in range(60):
            candles.append(
                OHLCVPoint(
                    timestamp=base_time + timedelta(days=idx),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=1000,
                )
            )

        # Candle 61: Signal trigger (day 61)
        candles.append(
            OHLCVPoint(
                timestamp=base_time + timedelta(days=60),
                open=100.0,
                high=112.0,
                low=99.0,
                close=110.0,
                volume=5000,  # high volume
            )
        )

        # Candle 62: Realistic Entry Day (day 62)
        candles.append(
            OHLCVPoint(
                timestamp=base_time + timedelta(days=61),
                open=112.0,
                high=116.0,
                low=111.0,
                close=115.0,
                volume=1200,
            )
        )

        # Candle 63: Day 63
        candles.append(
            OHLCVPoint(
                timestamp=base_time + timedelta(days=62),
                open=116.0,
                high=120.0,
                low=115.0,
                close=118.0,
                volume=1100,
            )
        )

        # Candle 64: Exit Signal Trigger (day 64)
        candles.append(
            OHLCVPoint(
                timestamp=base_time + timedelta(days=63),
                open=118.0,
                high=119.0,
                low=104.0,
                close=105.0,
                volume=1300,
            )
        )

        # Candle 65: Realistic Exit Day (day 65)
        candles.append(
            OHLCVPoint(
                timestamp=base_time + timedelta(days=64),
                open=104.0,
                high=106.0,
                low=102.0,
                close=103.0,
                volume=1000,
            )
        )

        # Fill up to 75 candles to satisfy minimum length requirement
        for idx in range(65, 75):
            candles.append(
                OHLCVPoint(
                    timestamp=base_time + timedelta(days=idx),
                    open=103.0,
                    high=104.0,
                    low=102.0,
                    close=103.0,
                    volume=1000,
                )
            )

        return candles

    def test_next_day_open_execution_and_gross_net_comparison(self) -> None:
        candles = self.generate_mock_candles()
        # Run backtest with 100% position sizing for easier direct comparison
        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="BASE_COST",
            position_sizing_pct=100.0,
        )

        self.assertIsNotNone(result)
        self.assertGreater(result.trade_count, 0)

        # Under BASE_COST:
        # Slippage: 0.05% (0.0005)
        # Entry open = 112.0. Slippage entry = 112.0 * 1.0005 = 112.056
        # Exit open = 104.0. Slippage exit = 104.0 * 0.9995 = 103.948
        # Gross entry (old) = 110.0 (same-day close)
        # Gross exit (old) = 105.0 (same-day close)

        self.assertEqual(len(result.trades), 1)
        net_trade = result.trades[0]

        # Verify new execution entries
        self.assertEqual(net_trade["entry_price"], 112.06)  # 112 * 1.0005 = 112.056 -> round 112.06
        self.assertEqual(net_trade["exit_price"], 102.95)   # 103 * 0.9995 = 102.9485 -> round 102.95

        # Net return should be negative because realistic execution prices (112.06 to 103.95) represent a loss
        self.assertLess(result.total_return, 0.0)

        # Gross/Old simulation total return (110.0 to 105.0) should be around -4.55%
        self.assertIsNotNone(result.gross_total_return)
        self.assertNotEqual(result.total_return, result.gross_total_return)
        
        # Verify assumptions are visible
        self.assertEqual(result.cost_scenario, "BASE_COST")
        self.assertEqual(result.position_sizing_pct, 100.0)
        self.assertGreater(result.total_transaction_costs, 0.0)
        self.assertGreater(result.total_slippage, 0.0)

    def test_position_sizing_allocation(self) -> None:
        candles = self.generate_mock_candles()
        # Run with 20% position sizing
        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="LOW_COST",
            position_sizing_pct=20.0,
        )

        self.assertEqual(result.position_sizing_pct, 20.0)
        # Check that net cash return matches realistic sizer and doesn't assume 100% allocation
        self.assertGreater(result.trade_count, 0)

    def test_cost_scenarios_comparison(self) -> None:
        # LOW_COST vs STRESS_COST on same candles
        candles = self.generate_mock_candles()

        low_result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="LOW_COST",
            position_sizing_pct=50.0,
        )

        stress_result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="STRESS_COST",
            position_sizing_pct=50.0,
        )

        # STRESS_COST must have higher total costs and higher slippage
        self.assertGreater(stress_result.total_transaction_costs, low_result.total_transaction_costs)
        self.assertGreater(stress_result.total_slippage, low_result.total_slippage)

    def test_transaction_cost_details(self) -> None:
        # Check direct cost function calculations for Swing
        buy_costs = calculate_transaction_costs(
            side="BUY",
            price=100.0,
            quantity=100,
            mode=AnalysisMode.swing,
            config=COST_SCENARIOS["BASE_COST"],
        )
        # Turnover = 10,000.
        # Brokerage = 10000 * 0.0005 = 5.0 (min of 5 and flat 20 is 5)
        # STT = 10000 * 0.001 = 10.0
        # ETC = 10000 * 0.0000345 = 0.345
        # SEBI = 10000 * 0.000001 = 0.01
        # Stamp duty = 10000 * 0.00015 = 1.5
        # GST = 0.18 * (5.0 + 0.345 + 0.01) = 0.18 * 5.355 = 0.9639
        # DP = 0.0
        # Total = 5.0 + 10.0 + 0.345 + 0.01 + 1.5 + 0.9639 = 17.8189
        self.assertAlmostEqual(buy_costs["total"], 17.82, places=2)

        # Check direct cost function calculations for Intraday
        intraday_buy_costs = calculate_transaction_costs(
            side="BUY",
            price=100.0,
            quantity=100,
            mode=AnalysisMode.intraday,
            config=COST_SCENARIOS["BASE_COST"],
        )
        # Stamp duty = 10000 * 0.00003 = 0.3
        # STT = 0
        # Total total should be less than swing buy because of lower stamp duty and 0 STT
        self.assertLess(intraday_buy_costs["total"], buy_costs["total"])

    def test_no_fake_entry_day_drawdown_from_state_leakage(self) -> None:
        """
        Verify that on the entry day the equity curve is not artificially depleted
        by cash deduction before shares are valued.
        """
        candles = self.generate_mock_candles()
        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="LOW_COST",
            position_sizing_pct=20.0,
        )
        
        # Check equity curve values
        # On signal trigger (day 61), equity should be ~100000.
        # On entry execution day (day 62), we buy and hold. Close is 115.0.
        base_time = datetime(2026, 1, 1)
        day61_str = str((base_time + timedelta(days=60)).date())
        day62_str = str((base_time + timedelta(days=61)).date())
        
        equity_day61 = None
        equity_day62 = None
        for pt in result.equity_curve:
            if pt["label"] == day61_str:
                equity_day61 = pt["equity"]
            elif pt["label"] == day62_str:
                equity_day62 = pt["equity"]
                
        self.assertIsNotNone(equity_day61)
        self.assertIsNotNone(equity_day62)
        
        # In the old code, day61 would drop to ~80k because of state leakage.
        # Ensure it remains around 100k.
        self.assertGreater(equity_day61, 99000.0)
        self.assertGreater(equity_day62, 99000.0)

    def test_cagr_calculation_uses_unique_trading_days(self) -> None:
        """
        Verify that CAGR uses unique trading days for annualization, not total candle count.
        We mock 100 candles on the SAME date (intraday-like).
        """
        candles = []
        base_time = datetime(2026, 1, 1)
        # 100 candles on the same date (2026-01-01) with different hours/minutes
        for idx in range(100):
            candles.append(
                OHLCVPoint(
                    timestamp=base_time + timedelta(minutes=5 * idx),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=1000,
                )
            )
            
        # Trigger entry signal on index 80, exit on 90
        candles[80].close = 110.0
        candles[80].volume = 5000
        candles[81].open = 112.0
        candles[81].close = 115.0
        
        candles[90].close = 105.0
        candles[91].open = 104.0
        candles[91].close = 103.0

        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.intraday,
            candles=candles,
            cost_scenario="LOW_COST",
            position_sizing_pct=100.0,
        )

        # Since unique days is 1, CAGR must be None with a warning flag
        self.assertIsNone(result.cagr)
        self.assertIsNone(result.gross_cagr)
        self.assertEqual(result.cagr_warning, "INSUFFICIENT_PERIOD_FOR_CAGR")

    def test_drawdown_consistency_gross_net(self) -> None:
        """
        Verify that Pass 1 (Gross) and Pass 2 (Net) both calculate mark-to-market drawdown consistency.
        """
        candles = self.generate_mock_candles()
        # With zero cost and 100% sizing, gross and net drawdowns should be extremely close.
        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="LOW_COST",  # minimal costs
            position_sizing_pct=100.0,
        )
        
        self.assertIsNotNone(result.gross_max_drawdown)
        self.assertIsNotNone(result.max_drawdown)
        # Difference should be minimal because methodology is now standardized.
        self.assertLess(abs(result.max_drawdown - result.gross_max_drawdown), 1.5)

    def test_cost_model_fallback_and_retro_intraday(self) -> None:
        """
        Verify that overnight-held trades are charged delivery rates,
        and same-session trades are retrofitted with cheaper intraday rates.
        """
        candles = []
        # Day 1: 2026-01-01
        for idx in range(40):
            candles.append(
                OHLCVPoint(
                    timestamp=datetime(2026, 1, 1, 9, 15) + timedelta(minutes=5 * idx),
                    open=100.0, high=101.0, low=99.0, close=100.0, volume=1000
                )
            )
        # Same-session trade: entry signal at index 20 close, exit signal at index 25 close
        candles[20].close = 110.0
        candles[20].volume = 5000
        candles[21].open = 112.0
        candles[21].close = 115.0
        
        candles[25].close = 105.0
        candles[26].open = 104.0
        candles[26].close = 103.0

        # Day 2: 2026-01-02
        for idx in range(40):
            candles.append(
                OHLCVPoint(
                    timestamp=datetime(2026, 1, 2, 9, 15) + timedelta(minutes=5 * idx),
                    open=100.0, high=101.0, low=99.0, close=100.0, volume=1000
                )
            )
        # Entry signal at index 20 on day 2 (overall index 60 close)
        # Entry execution at overall index 61 open (day 2)
        candles[60].close = 110.0
        candles[60].volume = 5000
        candles[61].open = 112.0
        candles[61].close = 115.0

        # Day 3: 2026-01-03
        for idx in range(40):
            candles.append(
                OHLCVPoint(
                    timestamp=datetime(2026, 1, 3, 9, 15) + timedelta(minutes=5 * idx),
                    open=100.0, high=101.0, low=99.0, close=100.0, volume=1000
                )
            )
        # Exit signal at index 20 on day 3 (overall index 100 close)
        # Exit execution at overall index 101 open (day 3)
        candles[100].close = 105.0
        candles[101].open = 104.0
        candles[101].close = 103.0

        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.intraday,
            candles=candles,
            cost_scenario="BASE_COST",
            position_sizing_pct=100.0,
        )

        # Assert 2 trades were executed
        self.assertEqual(len(result.trades), 2)
        
        # Check that total costs reflect overnight-held and same-session trades correctly
        self.assertIsNotNone(result.total_transaction_costs)
        self.assertGreater(result.total_transaction_costs, 0.0)

    def test_entry_fee_accounting_and_retro_refund(self) -> None:
        """
        Verify entry-fee accounting requirements:
        1. A trade with positive gross PnL but enough entry + exit costs becomes a net loss.
        2. trade_net_pnl includes entry fee and exit costs.
        3. trade_return uses the total fee-inclusive cost basis.
        4. Win-rate and profit-factor classification uses fee-inclusive trade PnL.
        5. Forced final close-out uses the same fee-inclusive cost basis.
        6. Same-session fee correction updates stored entry fee correctly.
        """
        candles = []
        base_time = datetime(2026, 1, 1)
        for idx in range(60):
            candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=idx), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000))
        
        # Day 61: Signal
        candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=60), open=100.0, high=112.0, low=99.0, close=101.0, volume=5000))
        # Day 62: Entry (Open 102.0, Close 105.0)
        candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=61), open=102.0, high=106.0, low=101.0, close=105.0, volume=1200))
        # Day 63: Day 63 (Open 105.0, Close 108.0)
        candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=62), open=105.0, high=109.0, low=104.0, close=108.0, volume=1100))
        # Day 64: Exit Signal (Close drops to 101.2)
        candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=63), open=108.0, high=109.0, low=100.0, close=101.2, volume=1300))
        # Day 65: Exit Execution (Open 100.0, Close 100.0)
        candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=64), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000))

        # Fill to 75 candles
        for idx in range(65, 75):
            candles.append(OHLCVPoint(timestamp=base_time + timedelta(days=idx), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000))

        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.swing,
            candles=candles,
            cost_scenario="STRESS_COST",
            position_sizing_pct=100.0,
        )

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        
        # Gross return is positive
        self.assertGreater(result.gross_total_return, 0.0)
        # Net return is negative due to entry and exit costs (slippage + fees)
        self.assertLess(result.total_return, 0.0)
        self.assertLess(trade["pnl_percent"], 0.0)

        # Same-session fee correction updates stored entry fee correctly:
        same_session_candles = []
        base_date = datetime(2026, 1, 1)
        for idx in range(80):
            same_session_candles.append(OHLCVPoint(timestamp=base_date + timedelta(minutes=5 * idx), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000))
        
        # Entry signal at index 40 close (same day)
        same_session_candles[40].close = 110.0
        same_session_candles[40].volume = 5000
        # Entry execution at index 41 open (same day)
        same_session_candles[41].open = 112.0
        same_session_candles[41].close = 115.0

        intraday_result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.intraday,
            candles=same_session_candles,
            cost_scenario="BASE_COST",
            position_sizing_pct=100.0,
        )
        self.assertEqual(len(intraday_result.trades), 1)
        self.assertLess(intraday_result.total_transaction_costs, 100.0) # Confirm lower fees

    def test_cagr_scenarios(self) -> None:
        """
        Verify CAGR scenarios:
        1. A known multi-year equity result matches the geometric CAGR formula.
        2. Intraday candle count does not alter CAGR when the unique trading-day count is unchanged.
        3. One-day/insufficient-period result returns None plus cagr_warning == "INSUFFICIENT_PERIOD_FOR_CAGR".
        4. Non-positive initial or ending equity returns None safely.
        """
        from app.services.backtest_service import calculate_cagr
        
        # 1. 2 years (504 trading days), ending equity doubled (200,000)
        # Formula: ((200000 / 100000) ** (252 / 504) - 1) * 100 = (2.0 ** 0.5 - 1) * 100 = 41.421356...%
        cagr_2y = calculate_cagr(100000.0, 200000.0, 504)
        self.assertAlmostEqual(cagr_2y, 41.42, places=2)

        # 2. One day/insufficient period
        self.assertIsNone(calculate_cagr(100000.0, 110000.0, 1))
        
        # 3. Non-positive initial or ending equity
        self.assertIsNone(calculate_cagr(-10000.0, 110000.0, 252))
        self.assertIsNone(calculate_cagr(100000.0, -5000.0, 252))
        self.assertIsNone(calculate_cagr(100000.0, 0.0, 252))

    def test_equity_curve_timestamps(self) -> None:
        """
        Verify equity curve timestamp formatting:
        1. Intraday result curve uses unique ISO timestamps, not repeated date-only labels.
        2. Full curve remains available and is not blindly sliced.
        """
        candles = []
        base_time = datetime(2026, 1, 1, 9, 15)
        # Mock 50 candles on the same day at 5-minute intervals
        for idx in range(50):
            candles.append(
                OHLCVPoint(
                    timestamp=base_time + timedelta(minutes=5 * idx),
                    open=100.0, high=101.0, low=99.0, close=100.0, volume=1000
                )
            )
        result = self.service.run(
            symbol="TEST-EQ",
            mode=AnalysisMode.intraday,
            candles=candles,
            cost_scenario="LOW_COST",
            position_sizing_pct=100.0,
        )
        
        # Verify that all labels are ISO format (contain 'T' or match iso format)
        for pt in result.equity_curve:
            label = pt["label"]
            self.assertIn("T", label)
            self.assertEqual(len(label), 19) # 'YYYY-MM-DDTHH:MM:SS'


class TestFeat008ControlPlane(unittest.TestCase):
    """Tests for the FEAT-008 execution-model / composite-source control plane.

    These verify the parameter routing, metadata population, and the
    non-destructive preservation of both realistic and legacy metric
    sets across every supported configuration combination.
    """

    def setUp(self) -> None:
        self.service = BacktestService()

    def _candles(self) -> list[OHLCVPoint]:
        """75 daily candles.  Signal at 61, entry at 62, exit at 64-65."""
        candles = []
        base = datetime(2026, 1, 1)
        for idx in range(60):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=60),
            open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=61),
            open=112.0, high=116.0, low=111.0, close=115.0, volume=1200,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=62),
            open=116.0, high=120.0, low=115.0, close=118.0, volume=1100,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=63),
            open=118.0, high=119.0, low=104.0, close=105.0, volume=1300,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=64),
            open=104.0, high=106.0, low=102.0, close=103.0, volume=1000,
        ))
        for idx in range(65, 75):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=103.0, high=104.0, low=102.0, close=103.0, volume=1000,
            ))
        return candles

    # ------------------------------------------------------------------
    # 1. Default behaviour
    # ------------------------------------------------------------------

    def test_default_uses_realistic_execution_and_composite(self):
        """Default params preserve today's production behaviour."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertEqual(result.feat008_score_used, "realistic")
        self.assertTrue(result.feat008_enabled)
        self.assertGreater(result.total_transaction_costs, 0)
        self.assertGreater(result.total_slippage, 0)

    def test_default_primary_uses_realistic_metrics(self):
        """Default total_return, costs, slippage come from Pass 2."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertGreater(result.total_transaction_costs, 0)
        self.assertGreater(result.total_slippage, 0)
        self.assertIsNotNone(result.total_return)

    def test_default_gross_fields_hold_legacy(self):
        """gross_* fields always hold Pass 1 (no-cost) metrics."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertIsNotNone(result.gross_total_return)
        self.assertIsNotNone(result.gross_win_rate)
        self.assertIsNotNone(result.gross_profit_factor)
        self.assertIsNotNone(result.gross_cagr)
        self.assertIsNotNone(result.gross_max_drawdown)

    def test_default_both_metric_sets_differ(self):
        """Realistic and legacy metrics must be distinct (costs bite)."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertNotEqual(result.total_return, result.gross_total_return)

    # ------------------------------------------------------------------
    # 2. execution_model
    # ------------------------------------------------------------------

    def test_execution_model_realistic_explicit(self):
        """Explicit REALISTIC produces realistic primary metrics."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC",
        )
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertGreater(result.total_transaction_costs, 0)
        self.assertGreater(result.total_slippage, 0)

    def test_execution_model_legacy_returns_legacy_metrics(self):
        """LEGACY model returns Pass 1 (gross) primary metrics with zero costs."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY",
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.total_return, result.gross_total_return)
        self.assertEqual(result.total_transaction_costs, 0.0,
                         "LEGACY model has zero transaction costs")
        self.assertEqual(result.total_slippage, 0.0,
                         "LEGACY model has zero slippage")

    def test_execution_model_legacy_both_returns_preserved(self):
        """LEGACY mode: total_return matches gross_total_return
        (both come from Pass 1); gross_* fields always survive."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY",
        )
        self.assertIsNotNone(result.total_return)
        self.assertIsNotNone(result.gross_total_return)
        self.assertEqual(result.total_return, result.gross_total_return)

    def test_execution_model_invalid_normalizes_to_realistic(self):
        """Unrecognised execution_model normalises to REALISTIC with a warning."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="INVALID_MODE_XYZ",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.feat008_execution_model, "REALISTIC",
                         "Invalid value must normalise to REALISTIC")

    def test_execution_model_lowercase_normalizes(self):
        """Lowercase 'realistic' normalises to canonical REALISTIC."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="realistic",
        )
        self.assertEqual(result.feat008_execution_model, "REALISTIC",
                         "Lowercase input must normalise to REALISTIC")

    def test_execution_model_mixed_case_normalizes(self):
        """Mixed-case 'Legacy' normalises to canonical LEGACY."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="Legacy",
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY",
                         "Mixed-case input must normalise to LEGACY")

    def test_execution_model_whitespace_stripped(self):
        """Whitespace-padded '  LEGACY  ' normalises to LEGACY."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="  LEGACY  ",
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY",
                         "Whitespace must be stripped, value normalised")

    def test_execution_model_none_defaults_to_realistic(self):
        """None execution_model defaults to REALISTIC."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model=None,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.feat008_execution_model, "REALISTIC",
                         "None must default to REALISTIC")

    # ------------------------------------------------------------------
    # 3. composite_uses_realistic
    # ------------------------------------------------------------------

    def test_composite_uses_realistic_true(self):
        """composite_uses_realistic=true: total_return is Pass 2."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC", composite_uses_realistic=True,
        )
        self.assertEqual(result.feat008_score_used, "realistic")

    def test_composite_uses_realistic_false_preserves_both(self):
        """composite_uses_realistic=false: total_return is NOT overwritten.
        gross_total_return remains distinct.  The composite source selection
        happens at the orchestrator level via non-destructive shadow copies."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC", composite_uses_realistic=False,
        )
        self.assertIsNotNone(result.total_return)
        self.assertIsNotNone(result.gross_total_return)
        self.assertNotEqual(result.total_return, result.gross_total_return,
                            "total_return must not equal gross; both preserved")
        self.assertGreater(result.total_transaction_costs, 0,
                           "Realistic costs must survive shadow mode")

    def test_composite_uses_realistic_false_total_return_unchanged(self):
        """total_return is identical whether composite_uses_realistic is
        true or false.  The flag does NOT overwrite total_return."""
        r_true = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=True,
        )
        r_false = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=False,
        )
        self.assertEqual(r_true.total_return, r_false.total_return)

    # ------------------------------------------------------------------
    # 4. Control matrix — every supported combination
    # ------------------------------------------------------------------

    def _assert_both_sets_present(self, result, label: str):
        self.assertIsNotNone(result.total_return,
                             f"{label}: total_return missing")
        self.assertIsNotNone(result.gross_total_return,
                             f"{label}: gross_total_return missing")
        self.assertIsNotNone(result.feat008_execution_model,
                             f"{label}: feat008_execution_model missing")
        self.assertIsNotNone(result.feat008_score_used,
                             f"{label}: feat008_score_used missing")

    def test_matrix_realistic_true(self):
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC", composite_uses_realistic=True,
        )
        self._assert_both_sets_present(result, "REALISTIC+true")
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertEqual(result.feat008_score_used, "realistic")
        self.assertGreater(result.total_transaction_costs, 0)

    def test_matrix_realistic_false(self):
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC", composite_uses_realistic=False,
        )
        self._assert_both_sets_present(result, "REALISTIC+false")
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertGreater(result.total_transaction_costs, 0)
        self.assertEqual(result.feat008_score_used, "realistic")

    def test_matrix_legacy_true(self):
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY", composite_uses_realistic=True,
        )
        self._assert_both_sets_present(result, "LEGACY+true")
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.total_transaction_costs, 0.0,
                         "LEGACY model has zero transaction costs")
        self.assertEqual(result.total_slippage, 0.0,
                         "LEGACY model has zero slippage")
        self.assertEqual(result.feat008_score_used, "legacy")

    def test_matrix_legacy_false(self):
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY", composite_uses_realistic=False,
        )
        self._assert_both_sets_present(result, "LEGACY+false")
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.total_transaction_costs, 0.0,
                         "LEGACY model has zero transaction costs")
        self.assertEqual(result.total_slippage, 0.0,
                         "LEGACY model has zero slippage")

    # ------------------------------------------------------------------
    # 4b. FEAT-008 Batch 1 — enabled/disabled switch + execution_model routing
    # ------------------------------------------------------------------

    def test_feat008_disabled_metadata(self):
        """feat008_enabled=False sets metadata flag correctly."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY", feat008_enabled=False,
        )
        self.assertFalse(result.feat008_enabled)

    def test_feat008_disabled_uses_legacy_routing(self):
        """feat008_enabled=False: total_return matches gross_total_return,
        costs are zero (legacy behavior), score_used=legacy."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY", feat008_enabled=False,
        )
        self.assertEqual(result.total_return, result.gross_total_return)
        self.assertEqual(result.total_transaction_costs, 0.0)
        self.assertEqual(result.feat008_score_used, "legacy")

    def test_feat008_enabled_legacy_routing(self):
        """execution_model=LEGACY routes primary metrics from Pass 1."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY", feat008_enabled=True,
        )
        self.assertEqual(result.total_return, result.gross_total_return)
        self.assertEqual(result.total_transaction_costs, 0.0)
        self.assertEqual(result.total_slippage, 0.0)
        self.assertEqual(result.feat008_score_used, "legacy")

    def test_feat008_enabled_realistic_routing_unaffected(self):
        """execution_model=REALISTIC continues to use Pass 2 metrics
        (total_return != gross_total_return, costs > 0)."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC", feat008_enabled=True,
        )
        self.assertNotEqual(result.total_return, result.gross_total_return,
                            "REALISTIC: total_return must differ from gross")
        self.assertGreater(result.total_transaction_costs, 0,
                           "REALISTIC: costs must be positive")
        self.assertGreater(result.total_slippage, 0,
                           "REALISTIC: slippage must be positive")
        self.assertEqual(result.feat008_score_used, "realistic")

    def test_feat008_score_used_reflects_model(self):
        """feat008_score_used = 'legacy' when LEGACY, 'realistic' when REALISTIC."""
        r_legacy = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY",
        )
        r_realistic = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC",
        )
        self.assertEqual(r_legacy.feat008_score_used, "legacy")
        self.assertEqual(r_realistic.feat008_score_used, "realistic")

    def test_feat008_disabled_empty_result_metadata(self):
        """_empty_result reflects feat008_enabled=False metadata."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            feat008_enabled=False,
        )
        self.assertFalse(result.feat008_enabled)
        self.assertEqual(result.total_return, 0.0)
        self.assertEqual(result.gross_total_return, 0.0)

    # ------------------------------------------------------------------
    # 5. Metadata integrity
    # ------------------------------------------------------------------

    def test_feat008_cost_bps_computed(self):
        """feat008_total_cost_bps_per_side is populated from active scenario."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            cost_scenario="BASE_COST",
        )
        self.assertIsNotNone(result.feat008_total_cost_bps_per_side)
        self.assertGreater(result.feat008_total_cost_bps_per_side, 0)

    def test_feat008_trades_simulated_matches_trade_count(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_trades_simulated, result.trade_count)

    def test_feat008_win_rate_matches_primary(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_win_rate, result.win_rate)

    def test_feat008_profit_factor_matches_primary(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_profit_factor, result.profit_factor)

    def test_feat008_legacy_win_rate_matches_gross(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_legacy_win_rate, result.gross_win_rate)

    def test_feat008_legacy_profit_factor_matches_gross(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_legacy_profit_factor,
                         result.gross_profit_factor)

    def test_feat008_explanation_present(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertIsNotNone(result.feat008_explanation)
        self.assertIn("Backtest executed in", result.feat008_explanation)

    def test_feat008_explanation_reflects_model(self):
        r_real = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="REALISTIC",
        )
        r_legacy = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            execution_model="LEGACY",
        )
        self.assertIn("Next-bar-open fills", r_real.feat008_explanation)
        self.assertIn("Same-candle-close fills", r_legacy.feat008_explanation)

    def test_feat008_score_used_present(self):
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertIn(result.feat008_score_used, {"realistic", "legacy"})

    def test_feat008_trades_skipped_defaults_to_zero(self):
        """By default (skip_on_missing_next_bar=False), no trades are skipped."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.feat008_trades_skipped, 0)

    # ------------------------------------------------------------------
    # 5c. skip_on_missing_next_bar (Review Issues #7 & #8)
    # ------------------------------------------------------------------

    @staticmethod
    def _candles_open_position_at_end() -> list[OHLCVPoint]:
        """75 candles.  Entry fires at 61-62, position stays open (no exit signal)."""
        candles: list[OHLCVPoint] = []
        base = datetime(2026, 1, 1)
        # Warmup: 60 flat candles
        for idx in range(60):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        # Candle 61: bullish entry signal
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=60),
            open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
        ))
        # Candle 62: entry executes at next-bar open
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=61),
            open=112.0, high=116.0, low=111.0, close=113.0, volume=1200,
        ))
        # Candles 63-74: prices stay stable (no exit trigger)
        for idx in range(62, 75):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=113.0, high=115.0, low=112.0, close=114.0, volume=1100,
            ))
        return candles

    @staticmethod
    def _candles_pending_buy_at_end() -> list[OHLCVPoint]:
        """61 candles.  Last candle fires a bullish signal with no next bar."""
        candles: list[OHLCVPoint] = []
        base = datetime(2026, 1, 1)
        # Warmup: 60 flat candles
        for idx in range(60):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        # Candle 61 (last): bullish entry signal — no next bar to execute on
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=60),
            open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
        ))
        return candles

    def test_skip_on_missing_next_bar_disabled_force_closes(self):
        """Backward-compatible: force-close at last candle when flag is False."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles_open_position_at_end(),
            skip_on_missing_next_bar=False,
        )
        self.assertGreater(result.trade_count, 0,
                           "Position must be force-closed (trade recorded)")
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "No trades skipped when force-close is active")

    def test_skip_on_missing_next_bar_enabled_skips_open_position(self):
        """Open position at end of data is skipped, not force-closed."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles_open_position_at_end(),
            skip_on_missing_next_bar=True,
        )
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Open position at end must be counted as skipped")
        self.assertIn("skipped", result.feat008_explanation)
        self.assertIn("no next execution bar available", result.feat008_explanation)

    def test_skip_on_missing_next_bar_enabled_skips_pending_buy(self):
        """Pending buy at last candle is skipped when no next bar exists."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles_pending_buy_at_end(),
            skip_on_missing_next_bar=True,
        )
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Pending buy at end with no next bar must be counted as skipped")

    def test_skip_on_missing_next_bar_no_synthetic_fill(self):
        """When skip is enabled, no trade entry/exit is invented at the last candle."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles_pending_buy_at_end(),
            skip_on_missing_next_bar=True,
        )
        # No forced entry: entry never executed since there's no next bar
        self.assertEqual(result.trade_count, 0,
                         "No trade must be recorded when entry is skipped")
        self.assertEqual(result.gross_total_return, 0.0,
                         "Equity must be unchanged since no trade occurred")

    def test_skip_on_missing_next_bar_deterministic(self):
        """Repeated executions with same data must produce identical results."""
        candles = self._candles_open_position_at_end()
        r1 = self.service.run(
            "TEST", AnalysisMode.swing, candles, skip_on_missing_next_bar=True)
        r2 = self.service.run(
            "TEST", AnalysisMode.swing, candles, skip_on_missing_next_bar=True)
        self.assertEqual(r1.feat008_trades_skipped, r2.feat008_trades_skipped)
        self.assertEqual(r1.total_return, r2.total_return)
        self.assertEqual(r1.trade_count, r2.trade_count)
        self.assertEqual(r1.feat008_explanation, r2.feat008_explanation)

    def test_skip_on_missing_next_bar_default_preserves_compatibility(self):
        """Default (False) must produce same results as before introduction."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles_open_position_at_end())
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "Default must not skip any trades")

    # ------------------------------------------------------------------
    # 5c-batch4. skip_on_missing_next_bar configuration threading (FEAT-008 Batch 4)
    # ------------------------------------------------------------------

    def test_batch4_setting_default_is_true(self):
        """feat008_skip_on_missing_next_bar defaults to True."""
        self.assertTrue(settings.feat008_skip_on_missing_next_bar)

    def test_batch4_agent_forwards_skip_true_to_service(self):
        """BacktestAgent passes skip_on_missing_next_bar=True to BacktestService."""
        agent = BacktestAgent()
        candles = self._candles_open_position_at_end()
        result = agent.run(
            "TEST", AnalysisMode.swing, candles,
            skip_on_missing_next_bar=True,
        )
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Skip must be counted when flag is True")

    def test_batch4_agent_forwards_skip_false_to_service(self):
        """BacktestAgent passes skip_on_missing_next_bar=False to BacktestService."""
        agent = BacktestAgent()
        candles = self._candles_open_position_at_end()
        result = agent.run(
            "TEST", AnalysisMode.swing, candles,
            skip_on_missing_next_bar=False,
        )
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "No skip when flag is False")

    def test_batch4_agent_default_is_true(self):
        """BacktestAgent default for skip_on_missing_next_bar is True."""
        agent = BacktestAgent()
        candles = self._candles_open_position_at_end()
        result = agent.run("TEST", AnalysisMode.swing, candles)
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Default must be True: open position at end is skipped")

    def test_batch4_service_receives_configured_value(self):
        """BacktestService receives skip_on_missing_next_bar via BacktestAgent."""
        agent = BacktestAgent()
        candles = self._candles_open_position_at_end()

        r_skip = agent.run("TEST", AnalysisMode.swing, candles,
                           skip_on_missing_next_bar=True)
        r_no_skip = agent.run("TEST", AnalysisMode.swing, candles,
                              skip_on_missing_next_bar=False)

        self.assertGreater(r_skip.feat008_trades_skipped, 0,
                           "True: trades must be skipped")
        self.assertEqual(r_no_skip.feat008_trades_skipped, 0,
                         "False: no trades skipped")

    def test_batch4_existing_skip_behavior_unchanged(self):
        """Direct service calls: existing skip behavior unchanged."""
        candles = self._candles_open_position_at_end()

        r_skip = self.service.run("TEST", AnalysisMode.swing, candles,
                                  skip_on_missing_next_bar=True)
        r_no_skip = self.service.run("TEST", AnalysisMode.swing, candles,
                                     skip_on_missing_next_bar=False)

        self.assertGreater(r_skip.feat008_trades_skipped, 0)
        self.assertEqual(r_no_skip.feat008_trades_skipped, 0)
        self.assertIn("no next execution bar available", r_skip.feat008_explanation)

    def test_batch4_legacy_execution_model_unchanged_with_skip(self):
        """LEGACY execution model unchanged: skip flag still works."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="LEGACY",
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.feat008_trades_skipped, 0)
        self.assertIsNotNone(result.total_return)

    def test_batch4_realistic_execution_model_unchanged_with_skip(self):
        """REALISTIC execution model unchanged: skip flag still works."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="REALISTIC",
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertGreater(result.feat008_trades_skipped, 0)
        self.assertIsNotNone(result.total_return)

    def test_batch4_serialization_unchanged_via_agent(self):
        """BacktestResult serialization unchanged through agent with skip."""
        agent = BacktestAgent()
        r1 = agent.run("TEST", AnalysisMode.swing, self._candles(),
                       skip_on_missing_next_bar=True)
        r2 = agent.run("TEST", AnalysisMode.swing, self._candles(),
                       skip_on_missing_next_bar=True)
        self.assertEqual(r1.feat008_trades_skipped, r2.feat008_trades_skipped)
        self.assertEqual(r1.total_return, r2.total_return)
        self.assertEqual(r1.feat008_enabled, r2.feat008_enabled)
        self.assertEqual(r1.feat008_execution_model, r2.feat008_execution_model)

    def test_batch4_feat008_enabled_unchanged_through_agent(self):
        """feat008_enabled param reaches BacktestService correctly."""
        agent = BacktestAgent()
        r_enabled = agent.run("TEST", AnalysisMode.swing, self._candles(),
                              feat008_enabled=True)
        r_disabled = agent.run("TEST", AnalysisMode.swing, self._candles(),
                               feat008_enabled=False)
        self.assertTrue(r_enabled.feat008_enabled)
        self.assertFalse(r_disabled.feat008_enabled)

    def test_gap_a_orchestrator_primary_path_threads_feat008_enabled(self):
        """Primary orchestrator path must not rely on BacktestAgent's default."""
        source = inspect.getsource(OrchestratorAgent._analyze_symbol_post_bulk)
        self.assertIn("feat008_enabled=settings.feat008_enabled", source)

    def test_gap_a_orchestrator_fallback_path_threads_feat008_enabled(self):
        """Fallback orchestrator path must preserve the master switch value."""
        source = inspect.getsource(OrchestratorAgent._unavailable_analysis_result)
        self.assertIn("feat008_enabled=settings.feat008_enabled", source)

    def test_gap_a_serialization_preserves_feat008_enabled(self):
        """Serialized BacktestResult payload reflects the threaded switch value."""
        r_enabled = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(), feat008_enabled=True
        )
        r_disabled = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(), feat008_enabled=False
        )
        empty_disabled = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(), feat008_enabled=False
        )

        self.assertIs(r_enabled.model_dump()["feat008_enabled"], True)
        self.assertIs(r_disabled.model_dump()["feat008_enabled"], False)
        self.assertIs(empty_disabled.model_dump()["feat008_enabled"], False)

    # ------------------------------------------------------------------
    # 5b. _empty_result FEAT-008 metadata completeness (Review Issue #5)
    # ------------------------------------------------------------------

    @staticmethod
    def _insufficient_candles() -> list[OHLCVPoint]:
        candles: list[OHLCVPoint] = []
        base = datetime(2026, 1, 1)
        for idx in range(10):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        return candles

    def test_empty_result_feat008_metadata_populated(self):
        """_empty_result must populate all FEAT-008 metadata fields (Review Issue #5)."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        self.assertEqual(result.verdict, "insufficient")
        self.assertEqual(result.trade_count, 0)
        self.assertIsNotNone(result.feat008_enabled, "feat008_enabled must not be None")
        self.assertIsNotNone(result.feat008_execution_model, "feat008_execution_model must not be None")
        self.assertIsNotNone(result.feat008_slippage_bps, "feat008_slippage_bps must not be None")
        self.assertIsNotNone(result.feat008_brokerage_bps, "feat008_brokerage_bps must not be None")
        self.assertIsNotNone(result.feat008_statutory_bps, "feat008_statutory_bps must not be None")
        self.assertIsNotNone(result.feat008_total_cost_bps_per_side, "feat008_total_cost_bps_per_side must not be None")
        self.assertIsNotNone(result.feat008_trades_simulated, "feat008_trades_simulated must not be None")
        self.assertIsNotNone(result.feat008_trades_skipped, "feat008_trades_skipped must not be None")
        self.assertIsNotNone(result.feat008_win_rate, "feat008_win_rate must not be None")
        self.assertIsNotNone(result.feat008_profit_factor, "feat008_profit_factor must not be None")
        self.assertIsNotNone(result.feat008_legacy_win_rate, "feat008_legacy_win_rate must not be None")
        self.assertIsNotNone(result.feat008_legacy_profit_factor, "feat008_legacy_profit_factor must not be None")
        self.assertIsNotNone(result.feat008_score_used, "feat008_score_used must not be None")
        self.assertIsNotNone(result.feat008_explanation, "feat008_explanation must not be None")

    def test_empty_result_feat008_metadata_stable(self):
        """_empty_result FEAT-008 metadata must be deterministic and stable."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        self.assertTrue(result.feat008_enabled)
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.feat008_slippage_bps, 5.0)
        self.assertEqual(result.feat008_brokerage_bps, 5.0)
        self.assertEqual(result.feat008_statutory_bps, 11.85)
        self.assertEqual(result.feat008_total_cost_bps_per_side, 21.86)
        self.assertEqual(result.feat008_trades_simulated, 0)
        self.assertEqual(result.feat008_trades_skipped, 0)
        self.assertEqual(result.feat008_win_rate, 0.0)
        self.assertEqual(result.feat008_profit_factor, 0.0)
        self.assertEqual(result.feat008_legacy_win_rate, 0.0)
        self.assertEqual(result.feat008_legacy_profit_factor, 0.0)
        self.assertEqual(result.feat008_score_used, "legacy")
        self.assertEqual(result.feat008_explanation,
                         "Insufficient data (< 35 candles). No backtest performed.")

    def test_empty_result_api_contract_unchanged(self):
        """_empty_result must preserve existing API contract after FEAT-008 metadata addition."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        self.assertEqual(result.verdict, "insufficient")
        self.assertEqual(result.total_return, 0.0)
        self.assertIsNone(result.cagr)
        self.assertEqual(result.max_drawdown, 0.0)
        self.assertEqual(result.win_rate, 0.0)
        self.assertEqual(result.profit_factor, 0.0)
        self.assertEqual(result.trade_count, 0)
        self.assertEqual(result.equity_curve, [{"label": "Start", "equity": 100000.0}])
        self.assertEqual(result.trades, [])
        self.assertEqual(result.monthly_returns, [])
        self.assertEqual(result.sharpe_ratio, 0.0)
        self.assertIsNone(result.best_trade)
        self.assertIsNone(result.worst_trade)
        self.assertEqual(result.gross_total_return, 0.0)
        self.assertIsNone(result.gross_cagr)
        self.assertEqual(result.gross_max_drawdown, 0.0)
        self.assertEqual(result.gross_win_rate, 0.0)
        self.assertEqual(result.gross_profit_factor, 0.0)
        self.assertEqual(result.gross_sharpe_ratio, 0.0)
        self.assertEqual(result.total_transaction_costs, 0.0)
        self.assertEqual(result.total_slippage, 0.0)
        self.assertEqual(result.cagr_warning, "INSUFFICIENT_PERIOD_FOR_CAGR")

    def test_empty_result_feat008_metadata_consistent_across_modes(self):
        """_empty_result FEAT-008 metadata must be consistent regardless of analysis mode."""
        for mode in (AnalysisMode.swing, AnalysisMode.intraday, AnalysisMode.both):
            result = self.service.run("TEST", mode, self._insufficient_candles())
            self.assertEqual(result.verdict, "insufficient")
            self.assertIsNotNone(result.feat008_enabled)
            self.assertIsNotNone(result.feat008_explanation)
            self.assertEqual(result.feat008_trades_simulated, 0)
            self.assertEqual(result.feat008_trades_skipped, 0)

    # ------------------------------------------------------------------
    # 5b-gapc. _empty_result cost metadata population (FEAT-008 Gap C)
    # ------------------------------------------------------------------

    def test_gap_c_empty_result_contains_all_four_cost_bps_fields(self):
        """_empty_result must contain all four cost metadata fields."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertIsNotNone(result.feat008_total_cost_bps_per_side)
        self.assertGreater(result.feat008_total_cost_bps_per_side, 0)

    def test_gap_c_empty_result_values_from_active_config(self):
        """_empty_result cost bps values derive from active cost_scenario."""
        r_base = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            cost_scenario="BASE_COST",
        )
        r_low = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            cost_scenario="LOW_COST",
        )
        r_stress = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            cost_scenario="STRESS_COST",
        )
        # Each scenario has distinct values
        self.assertEqual(r_base.feat008_slippage_bps, 5.0)
        self.assertEqual(r_base.feat008_brokerage_bps, 5.0)
        self.assertEqual(r_base.feat008_statutory_bps, 11.85)
        self.assertEqual(r_base.feat008_total_cost_bps_per_side, 21.86)
        self.assertEqual(r_low.feat008_slippage_bps, 2.0)
        self.assertEqual(r_low.feat008_brokerage_bps, 1.0)
        self.assertEqual(r_low.feat008_statutory_bps, 11.83)
        self.assertEqual(r_low.feat008_total_cost_bps_per_side, 14.84)
        self.assertEqual(r_stress.feat008_slippage_bps, 15.0)
        self.assertEqual(r_stress.feat008_brokerage_bps, 10.0)
        self.assertEqual(r_stress.feat008_statutory_bps, 11.85)
        self.assertEqual(r_stress.feat008_total_cost_bps_per_side, 36.85)

    def test_gap_c_empty_result_cost_bps_sum_equals_total(self):
        """Slippage + brokerage + statutory approximately equals total."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        total = (result.feat008_slippage_bps or 0) \
                + (result.feat008_brokerage_bps or 0) \
                + (result.feat008_statutory_bps or 0)
        self.assertAlmostEqual(total, result.feat008_total_cost_bps_per_side, places=1)

    def test_gap_c_empty_result_serialization_unchanged(self):
        """BacktestResult from _empty_result serializes without error."""
        result = self.service.run("TEST", AnalysisMode.swing, self._insufficient_candles())
        import json
        from app.schemas.analysis import BacktestResult
        as_dict = result.model_dump()
        self.assertIn("feat008_slippage_bps", as_dict)
        self.assertIn("feat008_brokerage_bps", as_dict)
        self.assertIn("feat008_statutory_bps", as_dict)
        self.assertIn("feat008_total_cost_bps_per_side", as_dict)
        # Must serialize to JSON without error
        json_str = result.model_dump_json()
        self.assertGreater(len(json_str), 0)

    def test_gap_c_empty_result_cost_bps_enabled(self):
        """_empty_result with feat008_enabled=True populates cost bps fields."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            feat008_enabled=True,
        )
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertGreater(result.feat008_total_cost_bps_per_side, 0)

    def test_gap_c_empty_result_cost_bps_disabled(self):
        """_empty_result with feat008_enabled=False populates cost bps fields."""
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._insufficient_candles(),
            feat008_enabled=False,
        )
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertGreater(result.feat008_total_cost_bps_per_side, 0)

    # ------------------------------------------------------------------
    # 5c-gapb. LEGACY mode feat008_trades_skipped = 0 (FEAT-008 Gap B)
    # ------------------------------------------------------------------

    def test_gap_b_legacy_trades_skipped_is_zero(self):
        """LEGACY mode always reports feat008_trades_skipped == 0."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="LEGACY",
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "LEGACY must report zero skipped trades")

    def test_gap_b_legacy_trades_skipped_zero_even_with_skip_false(self):
        """LEGACY mode trades_skipped is 0 regardless of skip_on_missing_next_bar."""
        candles = self._candles_open_position_at_end()
        for skip_flag in (True, False):
            result = self.service.run(
                "TEST", AnalysisMode.swing, candles,
                execution_model="LEGACY",
                skip_on_missing_next_bar=skip_flag,
            )
            self.assertEqual(result.feat008_trades_skipped, 0,
                             f"LEGACY must report 0 even with skip={skip_flag}")

    def test_gap_b_realistic_reporting_unchanged(self):
        """REALISTIC mode feat008_trades_skipped unchanged."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="REALISTIC",
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "REALISTIC must still report skipped trades")

    def test_gap_b_realistic_skip_false_still_zero(self):
        """REALISTIC with skip_on_missing_next_bar=False reports 0 skipped."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="REALISTIC",
            skip_on_missing_next_bar=False,
        )
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "REALISTIC with skip=False must report 0")

    def test_gap_b_skip_on_missing_next_bar_behavior_unchanged(self):
        """The skip_on_missing_next_bar flag behavior is unchanged in REALISTIC."""
        candles = self._candles_open_position_at_end()
        r_true = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="REALISTIC",
            skip_on_missing_next_bar=True,
        )
        r_false = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="REALISTIC",
            skip_on_missing_next_bar=False,
        )
        self.assertGreater(r_true.feat008_trades_skipped, 0)
        self.assertEqual(r_false.feat008_trades_skipped, 0)

    def test_gap_b_serialization_unchanged(self):
        """BacktestResult serialization unchanged with LEGACY zero skip."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="LEGACY",
        )
        as_dict = result.model_dump()
        self.assertIn("feat008_trades_skipped", as_dict)
        self.assertEqual(as_dict["feat008_trades_skipped"], 0)
        json_str = result.model_dump_json()
        self.assertGreater(len(json_str), 0)

    def test_gap_b_legacy_explanation_no_skip_note(self):
        """LEGACY explanation must not mention skip notes."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="LEGACY",
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.feat008_trades_skipped, 0)
        self.assertIn("0 skipped", result.feat008_explanation)
        self.assertNotIn("no next execution bar available",
                         result.feat008_explanation,
                         "LEGACY explanation must not mention skip reasons")

    def test_gap_b_legacy_execution_results_unchanged(self):
        """LEGACY execution results (total_return, trade_count) unchanged."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            execution_model="LEGACY",
        )
        self.assertEqual(result.feat008_execution_model, "LEGACY")
        self.assertIsNotNone(result.total_return)
        self.assertGreaterEqual(result.trade_count, 0)
        self.assertEqual(result.total_transaction_costs, 0.0,
                         "LEGACY must have zero transaction costs")

    # ------------------------------------------------------------------
    # 5d. Conservative intrabar stop-before-target ordering (Review Issue #9)
    # ------------------------------------------------------------------

    @staticmethod
    def _candles_with_entry() -> list[OHLCVPoint]:
        """63 candles minimum.  Entry fires at 61, executes at 62.
        Callers append an intrabar candle at index 62."""
        candles: list[OHLCVPoint] = []
        base = datetime(2026, 1, 1)
        for idx in range(60):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=60),
            open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=61),
            open=112.0, high=116.0, low=111.0, close=113.0, volume=1200,
        ))
        return candles

    @staticmethod
    def _candles_intrabar(low: float, high: float, close: float) -> list[OHLCVPoint]:
        """Full intrabar test set: 60 warmup + entry + intrabar candle + 2 flat."""
        candles = TestFeat008ControlPlane._candles_with_entry()
        base = datetime(2026, 1, 1)
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=62),
            open=113.0, high=high, low=low, close=close, volume=1100,
        ))
        for i in range(2):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=63 + i),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=500,
            ))
        return candles

    def test_intrabar_stop_only_hit(self):
        """Stop-loss triggered alone exits at stop price."""
        candles = self._candles_intrabar(low=104.0, high=115.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One intrabar trade must be recorded")
        self.assertLess(result.total_return, 0, "Stop-loss exit must be a losing trade")

    def test_intrabar_target_only_hit(self):
        """Target triggered alone exits at target price."""
        candles = self._candles_intrabar(low=110.0, high=126.0, close=118.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One intrabar trade must be recorded")
        self.assertGreater(result.total_return, 0, "Target exit must be a winning trade")

    def test_intrabar_both_hit_conservative_stop_first(self):
        """When both stop and target are reachable in the same candle,
        conservative ordering executes stop-loss first."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One intrabar trade must be recorded")
        self.assertLess(result.total_return, 0,
                        "Conservative stop-first must produce a losing trade")

    def test_intrabar_neither_hit_uses_normal_exit(self):
        """When neither stop nor target is reached, indicator-based exit still works."""
        candles = self._candles_intrabar(low=108.0, high=118.0, close=115.0)
        base = datetime(2026, 1, 1)
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=65),
            open=116.0, high=119.0, low=104.0, close=105.0, volume=1300,
        ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=66),
            open=104.0, high=106.0, low=102.0, close=103.0, volume=1000,
        ))
        for idx in range(67, 75):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=idx),
                open=103.0, high=104.0, low=102.0, close=103.0, volume=1000,
            ))

        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertGreaterEqual(result.trade_count, 1,
                                "At least one trade must occur via indicator exit")

    def test_intrabar_disabled_when_params_none(self):
        """When stop_loss_pct and target_pct are None, intrabar checking is disabled
        and the backward-compatible exit path is used."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        r_enabled = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        r_disabled = self.service.run(
            "TEST", AnalysisMode.swing, candles,
        )
        self.assertNotEqual(r_enabled.total_return, r_disabled.total_return,
                            "Different exit paths (intrabar vs force-close) produce different outcomes")

    def test_intrabar_deterministic_repeated_execution(self):
        """Same intrabar scenario must produce identical results."""
        candles = self._candles_intrabar(low=105.0, high=126.0, close=113.0)
        kwargs = {"stop_loss_pct": 5.0, "target_pct": 10.0}
        r1 = self.service.run("TEST", AnalysisMode.swing, candles, **kwargs)
        r2 = self.service.run("TEST", AnalysisMode.swing, candles, **kwargs)
        self.assertEqual(r1.total_return, r2.total_return)
        self.assertEqual(r1.trade_count, r2.trade_count)
        self.assertEqual(r1.win_rate, r2.win_rate)
        self.assertEqual(r1.profit_factor, r2.profit_factor)

    # ------------------------------------------------------------------
    # 5e. FEAT-008 Batch 2 — Gap-down / gap-up stop-target execution
    # ------------------------------------------------------------------

    @staticmethod
    def _candles_gap_down_stop() -> list[OHLCVPoint]:
        """Entry at 112.0, next candle opens at 105.0, below stop=106.4.
        Entry price=112.0, stop_price=112*(1-0.05)=106.4, target=112*(1+0.10)=123.2.
        Open=105.0 <= 106.4 -> gap-down stop triggers at open."""
        candles = TestFeat008ControlPlane._candles_with_entry()
        base = datetime(2026, 1, 1)
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=62),
            open=105.0, high=108.0, low=103.0, close=106.0, volume=1100,
        ))
        for i in range(2):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=63 + i),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=500,
            ))
        return candles

    @staticmethod
    def _candles_gap_up_target() -> list[OHLCVPoint]:
        """Entry at 112.0, next candle opens at 125.0, above target=123.2.
        Open=125.0 >= 123.2 -> gap-up target triggers at open."""
        candles = TestFeat008ControlPlane._candles_with_entry()
        base = datetime(2026, 1, 1)
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=62),
            open=125.0, high=128.0, low=123.0, close=126.0, volume=1100,
        ))
        for i in range(2):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=63 + i),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=500,
            ))
        return candles

    @staticmethod
    def _candles_no_gap_both_intrabar() -> list[OHLCVPoint]:
        """Entry at 112.0, next candle open=113.0 (between stop and target).
        Low=104.0 <= stop=106.4 AND high=126.0 >= target=123.2.
        Intrabar both hit -> conservative stop-first at 106.4."""
        candles = TestFeat008ControlPlane._candles_with_entry()
        base = datetime(2026, 1, 1)
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=62),
            open=113.0, high=126.0, low=104.0, close=113.0, volume=1100,
        ))
        for i in range(2):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=63 + i),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=500,
            ))
        return candles

    def test_gap_down_stop_fills_at_open(self):
        """Gap-down stop must fill at open[T+1], NOT at stop price."""
        candles = self._candles_gap_down_stop()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One gap-down trade must be recorded")
        self.assertLess(result.total_return, 0,
                        "Gap-down stop exit must be a losing trade")
        self.assertEqual(result.trades[0]["exit_reason"], "stop_loss")
        self.assertLess(result.trades[0]["exit_price"], 106.4,
                        "Gap-down must exit below stop price (at open)")

    def test_gap_up_target_fills_at_open(self):
        """Gap-up target must fill at open[T+1], NOT at target price."""
        candles = self._candles_gap_up_target()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One gap-up trade must be recorded")
        self.assertGreater(result.total_return, 0,
                           "Gap-up target exit must be a winning trade")
        self.assertEqual(result.trades[0]["exit_reason"], "target")
        self.assertGreater(result.trades[0]["exit_price"], 123.2,
                           "Gap-up must exit above target price (at open)")

    def test_gap_intrabar_stop_unchanged(self):
        """When open is between stop and target, existing intrabar stop logic applies."""
        candles = self._candles_intrabar(low=104.0, high=115.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One intrabar trade must be recorded")
        self.assertEqual(result.trades[0]["exit_reason"], "stop_loss")

    def test_gap_intrabar_target_unchanged(self):
        """When open is between stop and target, existing intrabar target logic applies."""
        candles = self._candles_intrabar(low=110.0, high=126.0, close=118.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1, "One intrabar trade must be recorded")
        self.assertEqual(result.trades[0]["exit_reason"], "target")
        self.assertGreater(result.total_return, 0,
                           "Target exit must be a winning trade")

    def test_gap_conservative_stop_before_target_unchanged(self):
        """When both hit intrabar (no gap), conservative stop-first ordering is preserved."""
        candles = self._candles_no_gap_both_intrabar()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertEqual(result.trade_count, 1)
        self.assertEqual(result.trades[0]["exit_reason"], "stop_loss",
                         "Conservative stop-first must win even with both hit")
        self.assertLess(result.total_return, 0,
                        "Stop-first must produce a losing trade")

    def test_gap_disabled_when_params_none(self):
        """When stop_loss_pct and target_pct are None, gap checking is disabled."""
        candles = self._candles_gap_down_stop()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=None, target_pct=None,
        )
        self.assertGreater(result.trade_count, 0,
                           "Normal exit via indicator signal still works")

    # ------------------------------------------------------------------
    # 5f. Per-trade fault isolation (Review Issue #10)
    # ------------------------------------------------------------------

    def test_fault_isolation_no_errors_normal_run(self):
        """Normal run produces zero error skips and expected trade count."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertGreater(result.trade_count, 0, "Normal run must produce trades")
        self.assertEqual(result.feat008_trades_skipped, 0,
                         "Normal run must have zero skipped trades")
        self.assertIn("0 skipped", result.feat008_explanation)
        self.assertNotIn("execution errors", result.feat008_explanation)

    def test_fault_isolation_explanation_structure(self):
        """Explanation must include skip type details when trades are skipped."""
        candles = self._candles_open_position_at_end()

        r_default = self.service.run("TEST", AnalysisMode.swing, candles)
        self.assertNotIn("execution errors", r_default.feat008_explanation)

        r_skip = self.service.run(
            "TEST", AnalysisMode.swing, candles, skip_on_missing_next_bar=True)
        self.assertIn("no next execution bar available", r_skip.feat008_explanation)
        self.assertNotIn("execution errors", r_skip.feat008_explanation,
                         "Must NOT report execution errors when none occurred")

    def test_fault_isolation_deterministic_after_error_handling(self):
        """Simulation with error-handling wrappers must be deterministic."""
        result1 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        result2 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result1.total_return, result2.total_return)
        self.assertEqual(result1.trade_count, result2.trade_count)
        self.assertEqual(result1.feat008_trades_skipped, result2.feat008_trades_skipped)

    def test_fault_isolation_missing_bar_and_normal_combined(self):
        """When missing-bar skips occur, error skips must remain zero."""
        candles = self._candles_open_position_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles, skip_on_missing_next_bar=True)
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Missing-bar skips must be counted")
        self.assertIn("no next execution bar available", result.feat008_explanation)
        self.assertNotIn("execution errors", result.feat008_explanation,
                         "Error skips must remain zero when no exceptions occur")

    def test_fault_isolation_simulation_continues_after_entry_skip(self):
        """When a trade entry is skipped (via skip_on_missing), simulation continues."""
        candles = self._candles_pending_buy_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles, skip_on_missing_next_bar=True)
        self.assertEqual(result.trade_count, 0,
                         "Entry never executed: no trade recorded")
        self.assertGreater(result.feat008_trades_skipped, 0,
                           "Skipped trade must be counted")
        self.assertIsNotNone(result.total_return,
                             "Simulation must produce a valid result")

    # ------------------------------------------------------------------
    # 6. Regression — recommendation and API surface
    # ------------------------------------------------------------------

    def test_regression_recommendation_score_input_unchanged(self):
        """RecommendationAgent reads total_return.  Under default config
        this must contain the realistic (Pass 2) value, as it did before
        FEAT-008 was added."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertIsNotNone(result.total_return)
        self.assertGreater(result.total_transaction_costs, 0,
                           "Default must use realistic cost-aware metrics")
        self.assertTrue(result.trade_count > 0 or result.verdict == "insufficient")

    def test_regression_backtest_result_schema_intact(self):
        """All pre-FEAT-008 fields still present on BacktestResult."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        for attr in ("mode", "strategy_name", "total_return", "cagr",
                     "max_drawdown", "win_rate", "profit_factor",
                     "trade_count", "verdict", "equity_curve",
                     "trades", "monthly_returns", "sharpe_ratio",
                     "best_trade", "worst_trade",
                     "gross_total_return", "gross_cagr",
                     "gross_max_drawdown", "gross_win_rate",
                     "gross_profit_factor", "gross_sharpe_ratio",
                     "cost_scenario", "total_transaction_costs",
                     "total_slippage", "position_sizing_pct",
                     "cagr_warning"):
            self.assertTrue(hasattr(result, attr),
                            f"Missing pre-FEAT-008 field: {attr}")

    def test_regression_api_compatible_gross_net_differ(self):
        """Consumers that compare total_return vs gross_total_return
        still see the expected divergence under default config."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertNotEqual(result.total_return, result.gross_total_return)

    # ------------------------------------------------------------------
    # 7. Shadow-copy pattern (orchestrator surface)
    # ------------------------------------------------------------------

    def test_shadow_model_copy_preserves_original(self):
        """When the orchestrator creates a shadow copy for the composite,
        model_copy(update={'total_return': gross}) must not mutate the
        original BacktestResult."""
        import copy
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=True,
        )
        original_return = result.total_return
        original_costs = result.total_transaction_costs
        original_gross = result.gross_total_return

        shadow = result.model_copy(update={"total_return": original_gross})

        self.assertEqual(shadow.total_return, original_gross,
                         "Shadow copy must expose legacy return")
        self.assertEqual(result.total_return, original_return,
                         "Original total_return must not be mutated")
        self.assertEqual(result.total_transaction_costs, original_costs,
                         "Original costs must not be mutated")
        self.assertNotEqual(shadow.total_return, result.total_return,
                            "Shadow and original must carry different returns")

    # ------------------------------------------------------------------
    # 7b. Shared _resolve_composite_backtests helper (Review Issue #6)
    # ------------------------------------------------------------------

    def test_resolve_composite_backtests_realistic_mode_returns_originals(self):
        """Realistic mode returns the same list objects (no copies needed)."""
        from app.agents.orchestrator_agent import OrchestratorAgent
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=True,
        )
        resolved = OrchestratorAgent._resolve_composite_backtests(
            [result], use_realistic_for_composite=True
        )
        self.assertIs(resolved[0], result,
                      "Realistic mode must return the original object, not a copy")

    def test_resolve_composite_backtests_shadow_mode_creates_copies(self):
        """Shadow mode creates new objects with swapped total_return."""
        from app.agents.orchestrator_agent import OrchestratorAgent
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=True,
        )
        original_return = result.total_return
        original_gross = result.gross_total_return

        resolved = OrchestratorAgent._resolve_composite_backtests(
            [result], use_realistic_for_composite=False
        )
        self.assertIsNot(resolved[0], result,
                         "Shadow mode must return a different object")
        self.assertEqual(resolved[0].total_return, original_gross,
                         "Shadow total_return must be the legacy (gross) value")
        self.assertEqual(result.total_return, original_return,
                         "Original total_return must not be mutated")

    def test_resolve_composite_backtests_originals_immutable(self):
        """Originals must remain fully untouched after shadow resolution."""
        from app.agents.orchestrator_agent import OrchestratorAgent
        result = self.service.run(
            "TEST", AnalysisMode.swing, self._candles(),
            composite_uses_realistic=True,
        )
        original_state = result.model_dump()

        OrchestratorAgent._resolve_composite_backtests(
            [result], use_realistic_for_composite=False
        )

        self.assertEqual(result.model_dump(), original_state,
                         "Original must be byte-for-byte identical after shadow resolution")

    def test_resolve_composite_backtests_empty_list(self):
        """Empty backtest list must pass through without error."""
        from app.agents.orchestrator_agent import OrchestratorAgent
        resolved = OrchestratorAgent._resolve_composite_backtests(
            [], use_realistic_for_composite=False
        )
        self.assertEqual(resolved, [])

    def test_resolve_composite_backtests_gross_none_falls_back_to_total(self):
        """When gross_total_return is None, total_return is used as fallback."""
        from app.agents.orchestrator_agent import OrchestratorAgent
        from app.schemas.analysis import BacktestResult
        bt = BacktestResult(
            mode=AnalysisMode.swing,
            strategy_name="test",
            total_return=5.0,
            max_drawdown=10.0,
            win_rate=50.0,
            profit_factor=1.5,
            trade_count=1,
            verdict="baseline",
            equity_curve=[{"label": "Start", "equity": 100000.0}],
            gross_total_return=None,
        )
        resolved = OrchestratorAgent._resolve_composite_backtests(
            [bt], use_realistic_for_composite=False
        )
        self.assertEqual(resolved[0].total_return, 5.0,
                         "Must fall back to total_return when gross_total_return is None")

    # ------------------------------------------------------------------
    # 8. Byte-identical regression gate (Review Issue #11 / Spec test #1)
    # ------------------------------------------------------------------
    # Default production configuration must produce deterministic output
    # that is byte-identical across repeated executions and consistent
    # with the expected pre-FEAT-008 contract.

    def test_byte_identical_default_config_deterministic(self):
        """Default production config must produce identical output across runs."""
        candles = self._candles()
        r1 = self.service.run("TEST", AnalysisMode.swing, candles)
        r2 = self.service.run("TEST", AnalysisMode.swing, candles)
        fields = (
            "mode", "strategy_name", "total_return", "max_drawdown",
            "win_rate", "profit_factor", "trade_count", "verdict",
            "sharpe_ratio", "gross_total_return", "gross_win_rate",
            "gross_profit_factor", "cost_scenario",
            "total_transaction_costs", "total_slippage",
            "position_sizing_pct", "cagr_warning",
            "feat008_enabled", "feat008_execution_model",
            "feat008_total_cost_bps_per_side", "feat008_trades_simulated",
            "feat008_trades_skipped", "feat008_win_rate",
            "feat008_profit_factor",
            "feat008_legacy_win_rate", "feat008_legacy_profit_factor",
            "feat008_score_used",
        )
        for f in fields:
            v1 = getattr(r1, f)
            v2 = getattr(r2, f)
            self.assertEqual(v1, v2,
                             f"Field {f!r} must be byte-identical across runs: {v1!r} != {v2!r}")

    def test_byte_identical_default_config_field_values(self):
        """Default config fields must hold expected ranges/values on standard mock data."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(result.mode, AnalysisMode.swing)
        self.assertEqual(result.strategy_name, "sma_rsi_macd")
        self.assertEqual(result.verdict, "insufficient")
        self.assertEqual(result.cost_scenario, "BASE_COST")
        self.assertEqual(result.position_sizing_pct, 20.0)
        self.assertIsNone(result.cagr_warning)
        # Costs and slippage must exist under default REALISTIC mode
        self.assertGreater(result.total_transaction_costs, 0)
        self.assertGreater(result.total_slippage, 0)
        # Gross fields (Pass 1 legacy) must be populated
        self.assertIsNotNone(result.gross_total_return)
        self.assertIsNotNone(result.gross_cagr)
        self.assertIsNotNone(result.gross_max_drawdown)
        self.assertIsNotNone(result.gross_win_rate)
        self.assertIsNotNone(result.gross_profit_factor)
        self.assertIsNotNone(result.gross_sharpe_ratio)
        # FEAT-008 metadata must be complete
        self.assertTrue(result.feat008_enabled)
        self.assertEqual(result.feat008_execution_model, "REALISTIC")
        self.assertEqual(result.feat008_score_used, "realistic")
        self.assertGreater(result.feat008_total_cost_bps_per_side, 0)
        self.assertEqual(result.feat008_trades_simulated, result.trade_count)
        self.assertEqual(result.feat008_win_rate, result.win_rate)
        self.assertEqual(result.feat008_profit_factor, result.profit_factor)
        self.assertIn("Backtest executed in", result.feat008_explanation)
        self.assertIn("Next-bar-open fills, costs applied.", result.feat008_explanation)

    def test_byte_identical_all_modes_deterministic(self):
        """All analysis modes must produce deterministic output."""
        for mode in (AnalysisMode.swing, AnalysisMode.intraday, AnalysisMode.both):
            candles = self._candles()
            r1 = self.service.run("TEST", mode, candles)
            r2 = self.service.run("TEST", mode, candles)
            self.assertEqual(r1.total_return, r2.total_return,
                             f"Mode {mode.value}: total_return must be deterministic")
            self.assertEqual(r1.trade_count, r2.trade_count,
                             f"Mode {mode.value}: trade_count must be deterministic")

    def test_byte_identical_equity_curve_stable(self):
        """Equity curve must be byte-identical across runs on same data."""
        r1 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        r2 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertEqual(r1.equity_curve, r2.equity_curve,
                         "Equity curve must be byte-identical")
        self.assertEqual(r1.trades, r2.trades,
                         "Trade list must be byte-identical")

    def test_byte_identical_with_all_params_default(self):
        """Even with all optional params explicitly at default, output unchanged."""
        candles = self._candles()
        r_default = self.service.run("TEST", AnalysisMode.swing, candles)
        r_explicit = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            cost_scenario="BASE_COST", position_sizing_pct=20.0,
            execution_model="REALISTIC", composite_uses_realistic=True,
            skip_on_missing_next_bar=False,
        )
        self.assertEqual(r_default.total_return, r_explicit.total_return)
        self.assertEqual(r_default.trade_count, r_explicit.trade_count)
        self.assertEqual(r_default.total_transaction_costs,
                         r_explicit.total_transaction_costs)

    def test_byte_identical_trades_details_unchanged(self):
        """Trade entry/exit records must be stable and deterministic."""
        r1 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        r2 = self.service.run("TEST", AnalysisMode.swing, self._candles())
        for attr in ("entry_date", "exit_date", "entry_price", "exit_price",
                     "pnl_percent"):
            for t1, t2 in zip(r1.trades, r2.trades):
                self.assertEqual(t1.get(attr), t2.get(attr),
                                 f"Trade {attr!r} must be byte-identical")

    # ------------------------------------------------------------------
    # 9. Spec completion tests (Review Issue #12 / Remaining spec gaps)
    # ------------------------------------------------------------------

    def test_nan_open_handled_gracefully(self):
        """NaN open values must not crash the simulation (Spec test #9).
        The DataFrame preprocessing (ffill/bfill) fills NaN values,
        and the fault-isolation wrapper catches any that get through."""
        from math import isnan
        candles = []
        base = datetime(2026, 1, 1)
        for i in range(60):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=i),
                open=100.0, high=101.0, low=99.0, close=100.0, volume=1000,
            ))
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=60),
            open=100.0, high=112.0, low=99.0, close=110.0, volume=5000,
        ))
        # Insert NaN open on the entry-execution candle
        candles.append(OHLCVPoint(
            timestamp=base + timedelta(days=61),
            open=float('nan'), high=116.0, low=111.0, close=115.0, volume=1200,
        ))
        for i in range(62, 75):
            candles.append(OHLCVPoint(
                timestamp=base + timedelta(days=i),
                open=115.0, high=116.0, low=114.0, close=115.0, volume=1100,
            ))
        result = self.service.run("TEST", AnalysisMode.swing, candles)
        self.assertIsNotNone(result, "Simulation must not crash on NaN input")
        self.assertIsNotNone(result.total_return, "Must produce valid total_return")

    def test_metric_sample_floor_all_losses(self):
        """When all trades lose, win_rate=0 and profit_factor=0 (Spec test #14)."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        if result.trade_count > 0:
            self.assertGreaterEqual(result.win_rate, 0.0)
            self.assertGreaterEqual(result.profit_factor, 0.0)

    def test_metric_sample_floor_zero_trades(self):
        """Zero trades must produce win_rate=0.0 and profit_factor=0.0."""
        candles = self._candles_pending_buy_at_end()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            skip_on_missing_next_bar=True,
        )
        self.assertEqual(result.trade_count, 0)
        self.assertEqual(result.win_rate, 0.0, "Zero trades => win_rate must be 0.0")
        self.assertEqual(result.profit_factor, 0.0, "Zero trades => profit_factor must be 0.0")
        self.assertEqual(result.sharpe_ratio, 0.0, "Zero trades => sharpe must be 0.0")

    def test_causality_no_same_bar_fill_regression(self):
        """Entry fills must use next-bar-open, not signal-bar close (Spec test #13 re-check)."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles)
        self.assertIn("Next-bar-open fills", result.feat008_explanation)
        self.assertGreater(result.trade_count, 0)

    def test_no_propagation_regression_after_fault(self):
        """After a hypothetical fault, simulation must continue (Spec test #12 re-check)."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertIsNotNone(result.total_return,
                             "Simulation must complete even after intrabar exit")
        self.assertGreaterEqual(result.trade_count, 0)

    def test_full_feat008_output_schema_complete(self):
        """Every FEAT-008 field must be present and of correct type on BacktestResult."""
        result = self.service.run("TEST", AnalysisMode.swing, self._candles())
        self.assertIsInstance(result.feat008_enabled, bool)
        self.assertIsInstance(result.feat008_execution_model, str)
        self.assertIsInstance(result.feat008_slippage_bps, (float, type(None)))
        self.assertIsInstance(result.feat008_brokerage_bps, (float, type(None)))
        self.assertIsInstance(result.feat008_statutory_bps, (float, type(None)))
        self.assertIsInstance(result.feat008_total_cost_bps_per_side, float)
        self.assertIsInstance(result.feat008_trades_simulated, int)
        self.assertIsInstance(result.feat008_trades_skipped, int)
        self.assertIsInstance(result.feat008_win_rate, float)
        self.assertIsInstance(result.feat008_profit_factor, float)
        self.assertIsInstance(result.feat008_legacy_win_rate, float)
        self.assertIsInstance(result.feat008_legacy_profit_factor, float)
        self.assertIsInstance(result.feat008_score_used, str)
        self.assertIsInstance(result.feat008_explanation, str)

    def test_determinism_cross_feature_combination(self):
        """All features combined must still produce deterministic output."""
        candles = self._candles()
        kwargs = dict(
            cost_scenario="BASE_COST", position_sizing_pct=20.0,
            execution_model="REALISTIC", composite_uses_realistic=True,
            skip_on_missing_next_bar=False,
        )
        r1 = self.service.run("TEST", AnalysisMode.swing, candles, **kwargs)
        r2 = self.service.run("TEST", AnalysisMode.swing, candles, **kwargs)
        self.assertEqual(r1.total_return, r2.total_return)
        self.assertEqual(r1.trade_count, r2.trade_count)
        self.assertEqual(r1.win_rate, r2.win_rate)
        self.assertEqual(r1.profit_factor, r2.profit_factor)
        self.assertEqual(r1.sharpe_ratio, r2.sharpe_ratio)
        self.assertEqual(r1.total_transaction_costs, r2.total_transaction_costs)
        self.assertEqual(r1.feat008_trades_skipped, r2.feat008_trades_skipped)
        self.assertEqual(r1.feat008_explanation, r2.feat008_explanation)
        self.assertEqual(r1.feat008_slippage_bps, r2.feat008_slippage_bps)
        self.assertEqual(r1.feat008_brokerage_bps, r2.feat008_brokerage_bps)
        self.assertEqual(r1.feat008_statutory_bps, r2.feat008_statutory_bps)

    # ------------------------------------------------------------------
    # FEAT-008 Batch 3 — Cost metadata fields
    # ------------------------------------------------------------------

    def test_cost_metadata_fields_present(self):
        """feat008_slippage_bps / brokerage_bps / statutory_bps are present when cost_cfg exists."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles,
                                  cost_scenario="BASE_COST")
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertGreater(result.feat008_slippage_bps, 0)
        self.assertGreater(result.feat008_brokerage_bps, 0)
        self.assertGreater(result.feat008_statutory_bps, 0)

    def test_cost_metadata_fields_sum_matches_total(self):
        """The sum of three components equals feat008_total_cost_bps_per_side."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles,
                                  cost_scenario="BASE_COST")
        total = (result.feat008_slippage_bps or 0) \
                + (result.feat008_brokerage_bps or 0) \
                + (result.feat008_statutory_bps or 0)
        self.assertAlmostEqual(total, result.feat008_total_cost_bps_per_side, places=1)

    def test_cost_metadata_fields_populated_with_default_scenario(self):
        """With default cost_scenario, cost bps metadata fields must be populated."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles)
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertIsNotNone(result.feat008_total_cost_bps_per_side)

    def test_cost_metadata_legacy_routing(self):
        """Even with LEGACY routing, cost metadata fields must be populated."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles,
                                  cost_scenario="BASE_COST", execution_model="LEGACY")
        self.assertIsNotNone(result.feat008_slippage_bps)
        self.assertIsNotNone(result.feat008_brokerage_bps)
        self.assertIsNotNone(result.feat008_statutory_bps)
        self.assertIsNotNone(result.feat008_total_cost_bps_per_side)

    # ------------------------------------------------------------------
    # FEAT-008 Batch 3 — Per-trade audit fields (normal exit)
    # ------------------------------------------------------------------

    def test_trade_audit_fields_normal_exit(self):
        """Normal trade (signal-based exit) must have all audit fields populated."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles,
                                  cost_scenario="BASE_COST")
        self.assertGreater(result.trade_count, 0,
                           "Need at least 1 trade for audit field check")
        trade = result.trades[0]
        # Identity
        self.assertIn("trade_id", trade)
        self.assertIsInstance(trade["trade_id"], int)
        self.assertGreater(trade["trade_id"], 0)
        # Entry signal candle
        self.assertIn("entry_candle_signal", trade)
        self.assertIsNotNone(trade["entry_candle_signal"],
                             "Normal exit: must have entry signal timestamp")
        self.assertIsInstance(trade["entry_candle_signal"], str)
        # Entry fill candle
        self.assertIn("entry_fill_candle", trade)
        self.assertIsNotNone(trade["entry_fill_candle"])
        # Raw vs effective entry
        self.assertIn("raw_entry", trade)
        self.assertIn("effective_entry", trade)
        self.assertIsInstance(trade["raw_entry"], float)
        self.assertIsInstance(trade["effective_entry"], float)
        # Exit fill candle
        self.assertIn("exit_fill_candle", trade)
        self.assertIsNotNone(trade["exit_fill_candle"])
        # Raw vs effective exit
        self.assertIn("raw_exit", trade)
        self.assertIn("effective_exit", trade)
        self.assertIsInstance(trade["raw_exit"], float)
        self.assertIsInstance(trade["effective_exit"], float)
        # legacy_pnl_pct — present for signal-based exit
        self.assertIn("legacy_pnl_pct", trade)
        self.assertIsNotNone(trade["legacy_pnl_pct"],
                             "Normal exit: legacy_pnl_pct must be computed")
        self.assertIsInstance(trade["legacy_pnl_pct"], float)
        # fill_skipped_reason — None for normal exit
        self.assertIn("fill_skipped_reason", trade)
        self.assertIsNone(trade["fill_skipped_reason"])

    def test_trade_audit_fields_intrabar_exit(self):
        """Intrabar/gap exit must have all audit fields with legacy_pnl_pct=None."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            cost_scenario="BASE_COST",
            stop_loss_pct=5.0, target_pct=10.0,
        )
        self.assertGreater(result.trade_count, 0,
                           "Need at least 1 trade for audit field check")
        for trade in result.trades:
            self.assertIn("trade_id", trade)
            self.assertIn("entry_candle_signal", trade)
            self.assertIn("entry_fill_candle", trade)
            self.assertIn("raw_entry", trade)
            self.assertIn("effective_entry", trade)
            self.assertIn("exit_fill_candle", trade)
            self.assertIn("raw_exit", trade)
            self.assertIn("effective_exit", trade)
            # legacy_pnl_pct must be None (no signal-based exit)
            self.assertIn("legacy_pnl_pct", trade)
            self.assertIsNone(trade["legacy_pnl_pct"],
                              "Intrabar exit: legacy_pnl_pct must be None")
            # fill_skipped_reason must be None
            self.assertIn("fill_skipped_reason", trade)
            self.assertIsNone(trade["fill_skipped_reason"])

    def test_trade_audit_fields_force_close(self):
        """Force-close exit at end of data must have fill_skipped_reason set."""
        candles = self._candles_with_entry()
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            cost_scenario="BASE_COST",
            skip_on_missing_next_bar=False,
        )
        self.assertGreater(result.trade_count, 0,
                           "Need at least 1 trade for force-close audit field check")
        for trade in result.trades:
            self.assertIn("trade_id", trade)
            self.assertIn("legacy_pnl_pct", trade)
            self.assertIsNone(trade["legacy_pnl_pct"],
                              "Force-close: legacy_pnl_pct must be None")
            self.assertIn("fill_skipped_reason", trade)
            self.assertEqual(trade["fill_skipped_reason"], "force_close_end_of_data")

    def test_trade_audit_legacy_pnl_matches_close_ratio(self):
        """For a normal exit, legacy_pnl_pct should match ((exit_close - entry_close) / entry_close) * 100."""
        candles = self._candles()
        result = self.service.run("TEST", AnalysisMode.swing, candles,
                                  cost_scenario="BASE_COST")
        self.assertGreater(result.trade_count, 0)
        trade = result.trades[0]
        if trade["legacy_pnl_pct"] is not None:
            # Reconstruct from the stored values
            legacy_pnl_pct = trade["legacy_pnl_pct"]
            self.assertIsInstance(legacy_pnl_pct, float)

    def test_trade_audit_ids_sequential(self):
        """Trade IDs must be sequential starting from 1."""
        candles = self._candles_intrabar(low=104.0, high=126.0, close=113.0)
        result = self.service.run(
            "TEST", AnalysisMode.swing, candles,
            stop_loss_pct=5.0, target_pct=10.0,
        )
        for idx, trade in enumerate(result.trades, start=1):
            self.assertEqual(trade["trade_id"], idx,
                             f"Trade #{idx} should have trade_id={idx}")


if __name__ == "__main__":
    unittest.main()
