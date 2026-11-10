import asyncio
from abc import abstractmethod

from activity.activity import Activity
from activity.activity_base import AsyncActivityBase
from util import Pushable


class ActivityPushSubscriber(AsyncActivityBase, Pushable):
    def push(self, activity: Activity):
        try:
            self.activity_queue.put_nowait(activity)
        except asyncio.QueueFull:
            self.dropped += 1

    async def _run(self):
        while True:
            try:
                activity = await asyncio.wait_for(
                    self.activity_queue.get(),
                    timeout=self.inactivity_timeout,
                )
                await self.handle_push(activity)

            except TimeoutError:
                continue

    @abstractmethod
    async def handle_push(self, activity: Activity): ...
