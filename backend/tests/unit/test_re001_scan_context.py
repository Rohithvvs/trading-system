from app.services.re001.scan_context import (
    get_scan_run_id,
    new_scan_run_id,
    reset_scan_run_id,
    set_scan_run_id,
    set_user_id,
    get_user_id,
    reset_user_id,
)


def test_scan_run_id_context():
    assert get_scan_run_id() is None
    tok = set_scan_run_id(new_scan_run_id("x"))
    try:
        assert get_scan_run_id() is not None
        assert get_scan_run_id().startswith("x-")
    finally:
        reset_scan_run_id(tok)
    assert get_scan_run_id() is None


def test_user_id_context():
    tok = set_user_id("user-1")
    try:
        assert get_user_id() == "user-1"
    finally:
        reset_user_id(tok)
