"""Shortlist-only evaluation is an orchestrator concern; unit-level filter helper."""


def filter_shortlist(symbols: list[str], shortlist: set[str]) -> list[str]:
    return [s for s in symbols if s in shortlist]


def test_only_shortlist_symbols():
    matched = ["A", "B", "C", "D"]
    shortlist = {"B", "C"}
    assert filter_shortlist(matched, shortlist) == ["B", "C"]


def test_empty_shortlist():
    assert filter_shortlist(["A"], set()) == []
