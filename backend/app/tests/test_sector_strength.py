from __future__ import annotations

import copy
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.schemas.governance import SectorStrengthTelemetry, SectorStrengthItem
from types import SimpleNamespace

from app.services.sector_strength import (
    calculate_sector_strength,
    SectorInput,
    StockPriceReturn,
    _parse_sector_input,
    build_sector_strength_scan_inputs,
)
from app.services.shadow_executor import execute_shadow_sector_strength


def test_pure_sector_strength_outperforming():
    """Verify relative strength > +1.0% is labeled Outperforming."""
    sectors_data = [
        SectorInput(
            sector="NIFTY_IT",
            stocks=[
                StockPriceReturn(symbol="TCS", return_pct=2.5),
                StockPriceReturn(symbol="INFY", return_pct=2.0),
                StockPriceReturn(symbol="WIPRO", return_pct=1.5),
            ],
        )
    ]
    # Sector return average = 2.0%
    # Benchmark return = 0.5%
    # Relative strength = 2.0 - 0.5 = +1.5% (> 1.0%) -> Outperforming
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=0.5,
    )

    assert isinstance(telemetry, SectorStrengthTelemetry)
    assert telemetry.status == "success"
    assert len(telemetry.sectors) == 1

    sec = telemetry.sectors[0]
    assert sec.sector == "NIFTY_IT"
    assert sec.sector_return_pct == pytest.approx(2.0)
    assert sec.relative_strength == pytest.approx(1.5)
    assert sec.label == "Outperforming"
    assert sec.constituent_count == 3
    assert sec.confidence == "high"


def test_pure_sector_strength_underperforming():
    """Verify relative strength < -1.0% is labeled Underperforming."""
    sectors_data = [
        SectorInput(
            sector="NIFTY_BANK",
            stocks=[
                StockPriceReturn(symbol="HDFCBANK", return_pct=-1.5),
                StockPriceReturn(symbol="ICICIBANK", return_pct=-2.0),
                StockPriceReturn(symbol="SBIN", return_pct=-1.0),
            ],
        )
    ]
    # Sector return average = -1.5%
    # Benchmark return = 0.5%
    # Relative strength = -1.5 - 0.5 = -2.0% (< -1.0%) -> Underperforming
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=0.5,
    )

    sec = telemetry.sectors[0]
    assert sec.sector == "NIFTY_BANK"
    assert sec.sector_return_pct == pytest.approx(-1.5)
    assert sec.relative_strength == pytest.approx(-2.0)
    assert sec.label == "Underperforming"
    assert sec.confidence == "high"


def test_pure_sector_strength_neutral():
    """Verify relative strength within [-1.0%, +1.0%] is labeled Neutral."""
    sectors_data = [
        SectorInput(
            sector="NIFTY_AUTO",
            stocks=[
                StockPriceReturn(symbol="TATAMOTORS", return_pct=0.6),
                StockPriceReturn(symbol="M&M", return_pct=0.4),
                StockPriceReturn(symbol="MARUTI", return_pct=0.5),
            ],
        )
    ]
    # Sector return average = 0.5%
    # Benchmark return = 0.5%
    # Relative strength = 0.0% -> Neutral
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=0.5,
    )

    sec = telemetry.sectors[0]
    assert sec.relative_strength == pytest.approx(0.0)
    assert sec.label == "Neutral"
    assert sec.confidence == "high"


def test_low_confidence_handling():
    """Constituent count < 3 sets confidence='low' and relative_strength=None."""
    sectors_data = [
        SectorInput(
            sector="NIFTY_PHARMA",
            stocks=[
                StockPriceReturn(symbol="SUNPHARMA", return_pct=2.0),
                StockPriceReturn(symbol="CIPLA", return_pct=1.0),
            ],  # Only 2 stocks (< 3)
        )
    ]
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=0.5,
    )

    sec = telemetry.sectors[0]
    assert sec.constituent_count == 2
    assert sec.confidence == "low"
    assert sec.relative_strength is None
    assert sec.label == "Neutral"


def test_shadow_executor_isolation_and_exception_safety():
    """Verify execute_shadow_sector_strength handles empty sectors without raising."""
    # sectors=None is valid empty input (success + empty sectors), not an error path.
    execute_shadow_sector_strength(
        symbol="INVALID",
        sectors=None,
        stock_id=None,
    )


def test_build_sector_strength_scan_inputs_from_overlay_and_universe():
    """C2: scan input builder produces non-empty sectors + real benchmark from overlay."""
    tech_tcs = SimpleNamespace(indicators={"close": 102.0, "open": 100.0})
    tech_infy = SimpleNamespace(indicators={"change_pct": 1.5})
    tech_wipro = SimpleNamespace(indicators={"change_pct": 1.2})
    overlay = SimpleNamespace(
        mapped_sector="NSE:NIFTYIT-INDEX",
        sector_roc20=0.02,  # 2%
        nifty50_roc20=0.005,  # 0.5%
    )
    sectors, bench_sym, bench_ret = build_sector_strength_scan_inputs(
        universe_technical={"TCS": tech_tcs, "INFY": tech_infy, "WIPRO": tech_wipro},
        sector_overlay=overlay,
        mappings={
            "TCS": "NSE:NIFTYIT-INDEX",
            "INFY": "NSE:NIFTYIT-INDEX",
            "WIPRO": "NSE:NIFTYIT-INDEX",
        },
    )
    assert bench_sym == "NIFTY50"
    assert bench_ret == pytest.approx(0.5)
    assert len(sectors) >= 1
    it = next(s for s in sectors if s["sector"] == "NSE:NIFTYIT-INDEX")
    assert len(it["stocks"]) >= 3

    telemetry = calculate_sector_strength(
        sectors=sectors,
        benchmark_symbol=bench_sym,
        benchmark_return_pct=bench_ret,
    )
    assert telemetry.status == "success"
    assert len(telemetry.sectors) >= 1
    assert telemetry.sectors[0].relative_strength is not None


def test_build_sector_strength_scan_inputs_missing_benchmark():
    """Missing overlay benchmark yields None benchmark for low-confidence path."""
    sectors, _, bench = build_sector_strength_scan_inputs(
        universe_technical=None,
        sector_overlay=None,
    )
    assert sectors == []
    assert bench is None


def test_orchestrator_submits_sector_strength_with_real_scan_inputs(monkeypatch):
    """L3: orchestrator wires non-empty sector + benchmark into shadow sector_strength."""
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.schemas import AnalysisMode
    from app.services import shadow_executor as se
    from app.services.shadow_executor import execute_shadow_sector_strength

    captured: list[tuple] = []

    def _capture(fn, *args, **kwargs):
        captured.append((fn, args, kwargs))
        return None

    monkeypatch.setattr(se.ShadowThreadPool, "submit_task", staticmethod(_capture))

    agent = OrchestratorAgent.__new__(OrchestratorAgent)

    class _Tech:
        def __init__(self, change_pct: float):
            self.indicators = {"change_pct": change_pct}

    bulk = {
        AnalysisMode.swing: {
            "TCS": _Tech(2.0),
            "INFY": _Tech(1.8),
            "WIPRO": _Tech(1.5),
        }
    }
    overlay = SimpleNamespace(
        mapped_sector="NSE:NIFTYIT-INDEX",
        sector_roc20=0.02,
        nifty50_roc20=0.005,
    )

    agent._submit_shadow_candidate_features(
        symbol="TCS",
        stock_id=42,
        articles=[],
        bulk_technical_results=bulk,
        sector_overlay=overlay,
    )

    sector_calls = [c for c in captured if c[0] is execute_shadow_sector_strength]
    assert sector_calls, "expected execute_shadow_sector_strength submission"
    _fn, args, _kwargs = sector_calls[0]
    # args: symbol, sectors, benchmark_symbol, benchmark_return_pct, scan_time, stock_id
    assert args[0] == "TCS"
    sectors_arg = args[1]
    assert sectors_arg, "sectors must not be empty/None when overlay+universe present"
    assert args[2] == "NIFTY50"
    assert args[3] == pytest.approx(0.5)
    assert args[5] == 42


# ---------------------------------------------------------------------------
# Edge cases, isolation (FR-005..007, FR-011), boundary labels
# ---------------------------------------------------------------------------


def test_missing_benchmark_data_assigns_low_confidence_neutral():
    """Spec edge: missing benchmark → non-blocking low-confidence neutral metric."""
    sectors_data = [
        SectorInput(
            sector="NIFTY_IT",
            stocks=[
                StockPriceReturn(symbol="TCS", return_pct=2.0),
                StockPriceReturn(symbol="INFY", return_pct=2.0),
                StockPriceReturn(symbol="WIPRO", return_pct=2.0),
            ],
        )
    ]
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=None,
    )
    assert telemetry.status == "success"
    sec = telemetry.sectors[0]
    assert sec.confidence == "low"
    assert sec.relative_strength is None
    assert sec.label == "Neutral"
    # Live path would continue — calculation itself never raises


def test_empty_sectors_list_returns_success_with_empty_items():
    """Empty sector input yields success telemetry with zero sector rows."""
    telemetry = calculate_sector_strength(sectors=[], benchmark_return_pct=0.5)
    assert telemetry.status == "success"
    assert telemetry.sectors == []
    assert telemetry.benchmark_symbol == "NIFTY50"


def test_none_sectors_returns_success_with_empty_items():
    """None sectors is treated as empty input (no crash)."""
    telemetry = calculate_sector_strength(sectors=None, benchmark_return_pct=0.5)
    assert telemetry.status == "success"
    assert telemetry.sectors == []


def test_empty_stocks_in_sector():
    """Sector with zero constituents still emits a row with low confidence."""
    sectors_data = [SectorInput(sector="NIFTY_EMPTY", stocks=[])]
    telemetry = calculate_sector_strength(
        sectors=sectors_data,
        benchmark_return_pct=0.5,
    )
    assert len(telemetry.sectors) == 1
    sec = telemetry.sectors[0]
    assert sec.constituent_count == 0
    assert sec.sector_return_pct == pytest.approx(0.0)
    assert sec.confidence == "low"
    assert sec.relative_strength is None
    assert sec.label == "Neutral"


def test_boundary_relative_strength_exactly_one_percent_is_neutral():
    """RS == +1.0% and RS == -1.0% fall in Neutral band (not Out/Under)."""
    # avg sector = 1.5, bench = 0.5 → RS = 1.0
    out_boundary = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="BOUND_UP",
                stocks=[
                    StockPriceReturn(symbol="A", return_pct=1.5),
                    StockPriceReturn(symbol="B", return_pct=1.5),
                    StockPriceReturn(symbol="C", return_pct=1.5),
                ],
            )
        ],
        benchmark_return_pct=0.5,
    )
    assert out_boundary.sectors[0].relative_strength == pytest.approx(1.0)
    assert out_boundary.sectors[0].label == "Neutral"

    # avg sector = -0.5, bench = 0.5 → RS = -1.0
    under_boundary = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="BOUND_DN",
                stocks=[
                    StockPriceReturn(symbol="A", return_pct=-0.5),
                    StockPriceReturn(symbol="B", return_pct=-0.5),
                    StockPriceReturn(symbol="C", return_pct=-0.5),
                ],
            )
        ],
        benchmark_return_pct=0.5,
    )
    assert under_boundary.sectors[0].relative_strength == pytest.approx(-1.0)
    assert under_boundary.sectors[0].label == "Neutral"


def test_just_outside_neutral_band_labels():
    """RS slightly above +1.0 / below -1.0 flips Outperforming / Underperforming."""
    out_t = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="JUST_OUT",
                stocks=[
                    StockPriceReturn(symbol="A", return_pct=1.6),
                    StockPriceReturn(symbol="B", return_pct=1.6),
                    StockPriceReturn(symbol="C", return_pct=1.6),
                ],
            )
        ],
        benchmark_return_pct=0.5,  # RS = 1.1
    )
    assert out_t.sectors[0].label == "Outperforming"

    under_t = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="JUST_UNDER",
                stocks=[
                    StockPriceReturn(symbol="A", return_pct=-0.7),
                    StockPriceReturn(symbol="B", return_pct=-0.7),
                    StockPriceReturn(symbol="C", return_pct=-0.7),
                ],
            )
        ],
        benchmark_return_pct=0.5,  # RS = -1.2
    )
    assert under_t.sectors[0].label == "Underperforming"


def test_multiple_sectors_time_indexed_records():
    """Multiple sectors produce continuous per-sector rows (US2 scenario 3 shape)."""
    scan_time = datetime(2026, 7, 22, 10, 30, tzinfo=timezone.utc)
    telemetry = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="NIFTY_IT",
                stocks=[
                    StockPriceReturn(symbol="TCS", return_pct=2.0),
                    StockPriceReturn(symbol="INFY", return_pct=2.0),
                    StockPriceReturn(symbol="WIPRO", return_pct=2.0),
                ],
            ),
            SectorInput(
                sector="NIFTY_BANK",
                stocks=[
                    # avg -1.0 vs bench 0.5 → RS -1.5 → Underperforming
                    StockPriceReturn(symbol="HDFCBANK", return_pct=-1.0),
                    StockPriceReturn(symbol="ICICIBANK", return_pct=-1.0),
                    StockPriceReturn(symbol="SBIN", return_pct=-1.0),
                ],
            ),
        ],
        benchmark_return_pct=0.5,
        scan_time=scan_time,
    )
    assert telemetry.executed_at == scan_time.isoformat()
    assert len(telemetry.sectors) == 2
    by_name = {s.sector: s for s in telemetry.sectors}
    assert by_name["NIFTY_IT"].label == "Outperforming"
    assert by_name["NIFTY_IT"].relative_strength == pytest.approx(1.5)
    assert by_name["NIFTY_BANK"].label == "Underperforming"
    assert by_name["NIFTY_BANK"].relative_strength == pytest.approx(-1.5)


def test_dict_sector_input_parsing_with_alternate_keys():
    """Dict inputs with name/constituents/return keys parse successfully."""
    telemetry = calculate_sector_strength(
        sectors=[
            {
                "name": "NIFTY_FMCG",
                "constituents": [
                    {"symbol": "HINDUNILVR", "return": 1.2},
                    {"symbol": "ITC", "return_pct": 1.0},
                    {"symbol": "NESTLEIND", "return_pct": 0.8},
                ],
            }
        ],
        benchmark_return_pct=0.5,
    )
    assert len(telemetry.sectors) == 1
    sec = telemetry.sectors[0]
    assert sec.sector == "NIFTY_FMCG"
    assert sec.constituent_count == 3
    assert sec.confidence == "high"
    assert sec.sector_return_pct == pytest.approx(1.0)


def test_parse_sector_input_invalid_returns_none():
    """Invalid sector payloads are skipped without raising."""
    assert _parse_sector_input("not-a-sector") is None
    assert _parse_sector_input(123) is None
    assert _parse_sector_input(None) is None


def test_invalid_dict_sector_skipped_in_calculate():
    """Unparseable sector entries are skipped; valid ones still compute."""
    telemetry = calculate_sector_strength(
        sectors=[
            "bad-entry",
            SectorInput(
                sector="NIFTY_OK",
                stocks=[
                    StockPriceReturn(symbol="A", return_pct=3.0),
                    StockPriceReturn(symbol="B", return_pct=3.0),
                    StockPriceReturn(symbol="C", return_pct=3.0),
                ],
            ),
        ],
        benchmark_return_pct=0.5,
    )
    assert len(telemetry.sectors) == 1
    assert telemetry.sectors[0].sector == "NIFTY_OK"


def test_live_scoring_matrix_unaffected_by_sector_strength_calculation():
    """FR-006 / SC-002: sector strength pure calc never mutates live 100-point matrix state."""
    live_matrix = {
        "technical_score": 72.5,
        "sentiment_score": 0.61,
        "backtest_score": 68.0,
        "total_score": 81.0,
        "recommendation": "BUY",
        "confidence": 78.0,
    }
    live_snapshot = copy.deepcopy(live_matrix)

    # Callers pass sector data derived from market inputs — ensure pure function has no side effects
    sectors = [
        SectorInput(
            sector="NIFTY_IT",
            stocks=[
                StockPriceReturn(symbol="TCS", return_pct=2.5),
                StockPriceReturn(symbol="INFY", return_pct=2.0),
                StockPriceReturn(symbol="WIPRO", return_pct=1.5),
            ],
        )
    ]
    telemetry = calculate_sector_strength(sectors=sectors, benchmark_return_pct=0.5)

    assert live_matrix == live_snapshot
    assert telemetry.status == "success"
    # Telemetry is independent of scoring keys
    assert not hasattr(telemetry, "total_score")
    assert "recommendation" not in telemetry.model_dump()


def test_shadow_executor_does_not_mutate_caller_sector_inputs():
    """Shadow wrapper deep-copies inputs so live universe lists remain untouched (FR-011)."""
    stocks = [
        StockPriceReturn(symbol="TCS", return_pct=1.0),
        StockPriceReturn(symbol="INFY", return_pct=1.0),
        StockPriceReturn(symbol="WIPRO", return_pct=1.0),
    ]
    sectors = [SectorInput(sector="NIFTY_IT", stocks=stocks)]
    original = copy.deepcopy(sectors)

    with patch("app.services.shadow_executor._persist_shadow_key_telemetry") as persist:
        execute_shadow_sector_strength(
            symbol="TCS",
            sectors=sectors,
            benchmark_symbol="NIFTY50",
            benchmark_return_pct=0.2,
            stock_id=1,
        )
        persist.assert_called_once()
        kwargs = persist.call_args.kwargs
        assert kwargs["feature_key"] == "sector_strength"
        assert kwargs["symbol"] == "TCS"
        assert "executed_at" in kwargs["telemetry"]
        assert kwargs["telemetry"]["status"] == "success"

    assert sectors == original
    assert stocks == original[0].stocks


def test_shadow_executor_persist_failure_is_swallowed():
    """Persistence failures inside shadow path never propagate to live callers."""
    with patch(
        "app.services.shadow_executor._persist_shadow_key_telemetry",
        side_effect=RuntimeError("db down"),
    ):
        # Must not raise
        execute_shadow_sector_strength(
            symbol="TCS",
            sectors=[
                SectorInput(
                    sector="NIFTY_IT",
                    stocks=[
                        StockPriceReturn(symbol="TCS", return_pct=1.0),
                        StockPriceReturn(symbol="INFY", return_pct=1.0),
                        StockPriceReturn(symbol="WIPRO", return_pct=1.0),
                    ],
                )
            ],
            stock_id=99,
        )


def test_shadow_executor_calculation_exception_is_swallowed():
    """Calculation exceptions are logged and swallowed (SC-005 / FR-011)."""
    with patch(
        "app.services.shadow_executor.calculate_sector_strength",
        side_effect=ValueError("boom"),
    ):
        execute_shadow_sector_strength(symbol="FAIL", sectors=[], stock_id=1)


def test_telemetry_schema_fields_for_shadow_storage():
    """Sector strength payload matches data-model shadow_outputs schema keys."""
    telemetry = calculate_sector_strength(
        sectors=[
            SectorInput(
                sector="NIFTY_IT",
                stocks=[
                    StockPriceReturn(symbol="TCS", return_pct=2.0),
                    StockPriceReturn(symbol="INFY", return_pct=2.0),
                    StockPriceReturn(symbol="WIPRO", return_pct=2.0),
                ],
            )
        ],
        benchmark_symbol="NIFTY50",
        benchmark_return_pct=0.4,
    )
    payload = telemetry.model_dump()
    for key in ("executed_at", "status", "benchmark_symbol", "benchmark_return_pct", "sectors"):
        assert key in payload
    item = payload["sectors"][0]
    for key in (
        "sector",
        "sector_return_pct",
        "relative_strength",
        "label",
        "constituent_count",
        "confidence",
    ):
        assert key in item
    assert isinstance(item, dict)
    assert isinstance(telemetry.sectors[0], SectorStrengthItem)
