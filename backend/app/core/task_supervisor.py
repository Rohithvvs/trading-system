from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..utils import get_logger


class TaskSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._closing = False
        self._logger = get_logger("app.task_supervisor")

    def start(self, name: str, factory: Callable[[], Awaitable[None]]) -> None:
        if self._closing:
            return

        async def runner() -> None:
            while not self._closing:
                try:
                    await factory()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._logger.exception("Supervised task crashed | task=%s", name)
                    await asyncio.sleep(2)

        task = asyncio.create_task(runner(), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        self._closing = True
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

