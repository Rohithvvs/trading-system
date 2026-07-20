from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas.analysis import ShadowExecutionContext, ShadowExecutionResult


class IShadowExecutor(abc.ABC):
    @abc.abstractmethod
    async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
        """Runs the experimental ruleset logic against the provided snapshot context."""
        pass
