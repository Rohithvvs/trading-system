from __future__ import annotations

import pytest

from app.governance.experiment_cli import _parse_args


def test_parse_start():
    args = _parse_args(["start", "--name", "test-exp"])
    assert args.command == "start"
    assert args.name == "test-exp"


def test_parse_start_with_metadata():
    args = _parse_args(["start", "--name", "test", "--metadata", '{"key":"val"}'])
    assert args.command == "start"
    assert args.metadata == '{"key":"val"}'


def test_parse_pause():
    args = _parse_args(["pause"])
    assert args.command == "pause"


def test_parse_pause_with_id():
    args = _parse_args(["pause", "--id", "123e4567-e89b-12d3-a456-426614174000"])
    assert args.command == "pause"
    assert args.experiment_id == "123e4567-e89b-12d3-a456-426614174000"


def test_parse_resume():
    args = _parse_args(["resume"])
    assert args.command == "resume"


def test_parse_complete():
    args = _parse_args(["complete"])
    assert args.command == "complete"


def test_parse_fail():
    args = _parse_args(["fail", "--reason", "test failure"])
    assert args.command == "fail"
    assert args.reason == "test failure"


def test_parse_list():
    args = _parse_args(["list", "--status", "active", "--limit", "10"])
    assert args.command == "list"
    assert args.status == "active"
    assert args.limit == 10


def test_parse_show():
    args = _parse_args(["show", "some-uuid"])
    assert args.command == "show"
    assert args.experiment_id == "some-uuid"


def test_parse_metric():
    args = _parse_args(["metric", "--name", "cpu", "--value", "42.5", "--unit", "%"])
    assert args.command == "metric"
    assert args.name == "cpu"
    assert args.value == 42.5
    assert args.unit == "%"


def test_parse_audit_export():
    args = _parse_args(["audit", "export", "--format", "json"])
    assert args.command == "audit"
    assert args.audit_command == "export"
    assert args.format == "json"


def test_parse_audit_export_with_output():
    args = _parse_args([
        "audit", "export", "--format", "csv",
        "--since", "2026-01-01", "--output", "audit.csv",
    ])
    assert args.command == "audit"
    assert args.format == "csv"
    assert args.since == "2026-01-01"
    assert args.output == "audit.csv"
