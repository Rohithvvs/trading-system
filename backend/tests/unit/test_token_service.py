from __future__ import annotations

import pytest

from backend.app.services.token_service import _mask_token


@pytest.mark.unit
def test_mask_token_keeps_only_edges_visible():
    # Production: asterisks + last 4 (prefix/middle never exposed).
    masked = _mask_token("abcd1234wxyz")
    assert masked is not None
    assert masked.endswith("wxyz")
    assert "abcd" not in masked
    assert masked.startswith("*")
    assert _mask_token("short") == "*****"
    assert _mask_token(None) is None
