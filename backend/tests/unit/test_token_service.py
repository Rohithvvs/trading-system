from __future__ import annotations

import pytest

from backend.app.services.token_service import _mask_token


@pytest.mark.unit
def test_mask_token_keeps_only_edges_visible():
    assert _mask_token("abcd1234wxyz") == "abcd...wxyz"
    assert _mask_token("short") == "*****"
    assert _mask_token(None) is None
