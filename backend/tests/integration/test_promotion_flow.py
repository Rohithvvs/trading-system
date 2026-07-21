"""Integration tests for FEAT-012 Controlled Promotion Path.

Spec: specs/012-validation-minimal-promotion/spec.md
Covers FR-010..FR-014, US3 acceptance scenarios, SC-003/SC-004, CLI routes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.news_analysis_agent import NewsAnalysisAgent
from app.governance.rule_manager import RuleManager
from app.schemas.analysis import ArticleItem


@pytest.fixture(autouse=True)
def _reset_rule_manager_singleton() -> None:
    RuleManager.reset_instance()
    yield
    RuleManager.reset_instance()


@pytest.fixture()
def mock_news_articles() -> list[ArticleItem]:
    now = datetime.now(timezone.utc)
    return [
        ArticleItem(
            title="Stock market news: Reliance",
            description="Reliance shares hit record high",
            source="Moneycontrol",
            url="http://example.com/1",
            published_at=now,
            sentiment_score=0.8,
        ),
        ArticleItem(
            title="Stock market news: Reliance",  # Duplicate title
            description="Reliance shares hit record high again",
            source="Moneycontrol",
            url="http://example.com/2",
            published_at=now,
            sentiment_score=0.8,
        ),
        ArticleItem(
            title="Infosys earnings report",
            description="Infosys profit increases",
            source="Economic Times",
            url="http://example.com/3",
            published_at=now,
            sentiment_score=0.6,
        ),
    ]


def _force_state(state: str) -> RuleManager:
    """Force singleton cache to a known lifecycle state without disk I/O."""
    mgr = RuleManager()
    mgr._states["news_dedup"] = state
    return mgr


# ---------------------------------------------------------------------------
# US3 — pipeline routing by lifecycle state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_routing_shadow(mock_news_articles: list[ArticleItem]) -> None:
    """Shadow: original articles scored; shadow task submitted when hook enabled."""
    _force_state("shadow")
    agent = NewsAnalysisAgent()

    from app.config import settings

    original_shadow = settings.shadow_mode_enabled
    settings.shadow_mode_enabled = True
    try:
        with (
            patch.object(
                agent.news_service, "fetch_recent_news", return_value=mock_news_articles
            ),
            patch.object(
                agent.sentiment_service,
                "summarize",
                return_value=(0.8, "BUY", "Summary"),
            ) as mock_summarize,
            patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
        ):
            result_articles, score, label, summary = agent.run("RELIANCE-EQ")

            assert len(result_articles) == 3
            mock_summarize.assert_called_once_with("RELIANCE-EQ", mock_news_articles)
            mock_submit.assert_called_once()
            assert score == 0.8
            assert label == "BUY"
    finally:
        settings.shadow_mode_enabled = original_shadow


@pytest.mark.asyncio
async def test_pipeline_routing_production(mock_news_articles: list[ArticleItem]) -> None:
    """Production: deduplicated articles scored; shadow task bypassed (FR-011)."""
    _force_state("production")
    agent = NewsAnalysisAgent()

    with (
        patch.object(
            agent.news_service, "fetch_recent_news", return_value=mock_news_articles
        ),
        patch.object(
            agent.sentiment_service, "summarize", return_value=(0.8, "BUY", "Summary")
        ) as mock_summarize,
        patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
    ):
        result_articles, score, label, summary = agent.run("RELIANCE-EQ")

        assert len(result_articles) == 2
        assert result_articles[0].title == "Stock market news: Reliance"
        assert result_articles[1].title == "Infosys earnings report"
        mock_summarize.assert_called_once_with("RELIANCE-EQ", result_articles)
        mock_submit.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_routing_disabled(mock_news_articles: list[ArticleItem]) -> None:
    """Disabled: original articles scored; shadow task bypassed (FR-012)."""
    _force_state("disabled")
    agent = NewsAnalysisAgent()

    with (
        patch.object(
            agent.news_service, "fetch_recent_news", return_value=mock_news_articles
        ),
        patch.object(
            agent.sentiment_service, "summarize", return_value=(0.8, "BUY", "Summary")
        ) as mock_summarize,
        patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
    ):
        result_articles, score, label, summary = agent.run("RELIANCE-EQ")

        assert len(result_articles) == 3
        mock_summarize.assert_called_once_with("RELIANCE-EQ", mock_news_articles)
        mock_submit.assert_not_called()


# ---------------------------------------------------------------------------
# US3.3 / SC-003 / SC-004 — atomic switch between runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_switch_between_runs_is_atomic(
    mock_news_articles: list[ArticleItem],
) -> None:
    """Promote then kill between runs switches routing without pipeline failure."""
    mgr = _force_state("shadow")
    agent = NewsAnalysisAgent()

    from app.config import settings

    original_shadow = settings.shadow_mode_enabled
    settings.shadow_mode_enabled = True
    try:
        with (
            patch.object(
                agent.news_service, "fetch_recent_news", return_value=mock_news_articles
            ),
            patch.object(
                agent.sentiment_service,
                "summarize",
                return_value=(0.5, "HOLD", "Summary"),
            ) as mock_summarize,
            patch("app.services.shadow_executor.ShadowThreadPool.submit_task"),
        ):
            # Run 1: shadow → full article list
            arts1, *_ = agent.run("RELIANCE-EQ")
            assert len(arts1) == 3

            # Promote mid-session
            mgr._states["news_dedup"] = "production"
            arts2, *_ = agent.run("RELIANCE-EQ")
            assert len(arts2) == 2

            # Kill mid-session
            mgr._states["news_dedup"] = "disabled"
            arts3, *_ = agent.run("RELIANCE-EQ")
            assert len(arts3) == 3

            assert mock_summarize.call_count == 3
    finally:
        settings.shadow_mode_enabled = original_shadow


@pytest.mark.asyncio
async def test_shadow_hook_disabled_skips_background_task(
    mock_news_articles: list[ArticleItem],
) -> None:
    """When state is shadow but shadow hook is off, no background submit occurs."""
    _force_state("shadow")
    agent = NewsAnalysisAgent()

    from app.config import settings

    original_shadow = settings.shadow_mode_enabled
    settings.shadow_mode_enabled = False
    try:
        with (
            patch.object(
                agent.news_service, "fetch_recent_news", return_value=mock_news_articles
            ),
            patch.object(
                agent.sentiment_service,
                "summarize",
                return_value=(0.8, "BUY", "Summary"),
            ) as mock_summarize,
            patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
        ):
            result_articles, *_ = agent.run("RELIANCE-EQ")
            assert len(result_articles) == 3
            mock_summarize.assert_called_once()
            mock_submit.assert_not_called()
    finally:
        settings.shadow_mode_enabled = original_shadow


@pytest.mark.asyncio
async def test_empty_news_returns_neutral_without_routing_errors() -> None:
    """No articles: early return; rule state is not required for success path."""
    _force_state("production")
    agent = NewsAnalysisAgent()

    with (
        patch.object(agent.news_service, "fetch_recent_news", return_value=[]),
        patch.object(agent.sentiment_service, "summarize") as mock_summarize,
        patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
    ):
        articles, score, label, summary = agent.run("RELIANCE-EQ")
        assert articles == []
        assert score == 0.5
        assert label == "Neutral"
        assert "No recent news" in summary
        mock_summarize.assert_not_called()
        mock_submit.assert_not_called()


@pytest.mark.asyncio
async def test_production_path_uses_deduplicated_list_for_sentiment(
    mock_news_articles: list[ArticleItem],
) -> None:
    """SC-003: sentiment engine receives only the deduplicated list in production."""
    _force_state("production")
    agent = NewsAnalysisAgent()
    captured: dict = {}

    def _capture_summarize(symbol: str, articles: list) -> tuple:
        captured["count"] = len(articles)
        captured["titles"] = [a.title for a in articles]
        return 0.9, "BUY", "dedup path"

    with (
        patch.object(
            agent.news_service, "fetch_recent_news", return_value=mock_news_articles
        ),
        patch.object(agent.sentiment_service, "summarize", side_effect=_capture_summarize),
    ):
        agent.run("RELIANCE-EQ")

    assert captured["count"] == 2
    assert captured["titles"] == [
        "Stock market news: Reliance",
        "Infosys earnings report",
    ]


@pytest.mark.asyncio
async def test_kill_reverts_to_undeduplicated_on_next_run(
    mock_news_articles: list[ArticleItem],
) -> None:
    """SC-004: after kill, next run feeds original undeduplicated list."""
    mgr = _force_state("production")
    agent = NewsAnalysisAgent()

    with (
        patch.object(
            agent.news_service, "fetch_recent_news", return_value=mock_news_articles
        ),
        patch.object(
            agent.sentiment_service, "summarize", return_value=(0.5, "HOLD", "s")
        ) as mock_summarize,
        patch("app.services.shadow_executor.ShadowThreadPool.submit_task"),
    ):
        arts_prod, *_ = agent.run("RELIANCE-EQ")
        assert len(arts_prod) == 2

        mgr._states["news_dedup"] = "disabled"
        arts_disabled, *_ = agent.run("RELIANCE-EQ")
        assert len(arts_disabled) == 3
        # Last call used full undeduplicated list
        assert mock_summarize.call_args_list[-1].args[1] == mock_news_articles


# ---------------------------------------------------------------------------
# Governance route registration (FR-008)
# ---------------------------------------------------------------------------


def test_governance_routes_include_report_promote_kill() -> None:
    """experiment.report / promote / kill are registered in the governance router."""
    from app.governance.router import list_routes

    routes = list_routes()
    assert "experiment.report" in routes
    assert "experiment.promote" in routes
    assert "experiment.kill" in routes
    assert "report" in routes["experiment.report"]
    assert "promote" in routes["experiment.promote"]
    assert "kill" in routes["experiment.kill"]


def test_cli_parser_accepts_report_promote_kill_subcommands() -> None:
    """CLI argparse exposes report, promote, and kill subcommands with required flags."""
    from app.governance.experiment_cli import _parse_args

    report_args = _parse_args(["report", "--rule", "news_dedup"])
    assert report_args.command == "report"
    assert report_args.rule == "news_dedup"

    promote_args = _parse_args(
        ["promote", "--rule", "news_dedup", "--checklist-approved", "--reason", "ok"]
    )
    assert promote_args.command == "promote"
    assert promote_args.checklist_approved is True
    assert promote_args.reason == "ok"

    kill_args = _parse_args(["kill", "--rule", "news_dedup", "--reason", "anomaly"])
    assert kill_args.command == "kill"
    assert kill_args.reason == "anomaly"


def test_cli_promote_without_checklist_flag_defaults_false() -> None:
    """Promote parser leaves checklist_approved False when flag is omitted."""
    from app.governance.experiment_cli import _parse_args

    args = _parse_args(["promote", "--rule", "news_dedup"])
    assert args.checklist_approved is False


# ---------------------------------------------------------------------------
# End-to-end promote → production routing → kill → baseline routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_promote_route_kill_flow(
    mock_news_articles: list[ArticleItem], tmp_path: Path
) -> None:
    """Full lifecycle: promote via RuleManager, pipeline uses dedup, kill reverts."""
    states_file = tmp_path / "rule_states.json"
    audit_file = tmp_path / "audit.jsonl"
    from app.governance.audit import AuditTrailManager

    RuleManager.reset_instance()
    mgr = RuleManager(states_file=states_file)
    mgr.audit_mgr = AuditTrailManager(file_path=str(audit_file))

    await mgr.promote_rule(
        "news_dedup",
        checklist_approved=True,
        reason="E2E checklist complete",
        actor="e2e_admin",
    )
    assert mgr.is_active_in_production("news_dedup")

    agent = NewsAnalysisAgent()
    with (
        patch.object(
            agent.news_service, "fetch_recent_news", return_value=mock_news_articles
        ),
        patch.object(
            agent.sentiment_service, "summarize", return_value=(0.7, "BUY", "prod")
        ) as mock_summarize,
        patch("app.services.shadow_executor.ShadowThreadPool.submit_task") as mock_submit,
    ):
        arts, *_ = agent.run("RELIANCE-EQ")
        assert len(arts) == 2
        mock_submit.assert_not_called()

        await mgr.kill_rule("news_dedup", reason="E2E rollback", actor="e2e_admin")
        arts2, *_ = agent.run("RELIANCE-EQ")
        assert len(arts2) == 3
        assert mock_summarize.call_count == 2

    assert json_state(states_file) == "disabled"
    audit_text = audit_file.read_text(encoding="utf-8")
    assert "rule.promote" in audit_text
    assert "rule.kill" in audit_text


def json_state(path: Path) -> str:
    import json

    return json.loads(path.read_text(encoding="utf-8"))["news_dedup"]
