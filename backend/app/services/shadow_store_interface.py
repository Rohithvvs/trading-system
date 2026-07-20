from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas.analysis import ShadowComparisonLog


class IShadowStore(abc.ABC):
    @abc.abstractmethod
    async def save_comparison(self, comparison: ShadowComparisonLog) -> None:
        """Persists the comparative log using an isolated database session context."""
        pass
