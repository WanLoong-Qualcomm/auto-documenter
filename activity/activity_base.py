import asyncio
from abc import abstractmethod

from util import AsyncCleanupable


class AsyncActivityBase(AsyncCleanupable):
    def __init__(self, queue_size: int = 10, inactivity_timeout: int = 10):
        self.activity_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.inactivity_timeout: int = inactivity_timeout
        self.dropped: int = 0
        self._run_task: asyncio.Task = asyncio.create_task(self._run())

    @abstractmethod
    async def _run(self): ...

    async def cleanup(self):
        self._run_task.cancel()
        try:
            await self._run_task
        except asyncio.CancelledError:
            pass
