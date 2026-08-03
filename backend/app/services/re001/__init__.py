"""RE-001 Trend Continuation Recommendation Engine (lab / non-production).

Production shortlists and RecommendationService labels remain authoritative.
RE-001 runs isolated after production recommendation when enabled.
"""

from .registry import is_re001_active, get_re001_registration
from .runner import run_re001_isolated, run_re001_isolated_async

__all__ = [
    "is_re001_active",
    "get_re001_registration",
    "run_re001_isolated",
    "run_re001_isolated_async",
]
