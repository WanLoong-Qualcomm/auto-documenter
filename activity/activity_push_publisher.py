import asyncio
import time
from datetime import UTC, datetime

from pynput.keyboard import Listener as KeyboardListener
from pynput.mouse import Listener as MouseListener

from abstract import Pushable, Subscribable
from activity.activity import Activity, Inactivity, KeyboardActivity, MouseActivity
from activity.activity_base import AsyncActivityBase

DEFAULT_QUEUE_SIZE = 10
DEFAULT_INACTIVITY_TIMEOUT = 10


class ActivityPushPublisher(AsyncActivityBase, Subscribable):
    def __init__(
        self,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        inactivity_timeout: int = DEFAULT_INACTIVITY_TIMEOUT,
    ):
        super().__init__(queue_size, inactivity_timeout)
        self.subscribers: dict[type[Activity], list[Pushable]] = {}

    def subscribe(self, subscriber: Pushable, activity_types: list[type[Activity]]):
        for activity_type in activity_types:
            activity_subscribers = self.subscribers.get(activity_type)
            if not activity_subscribers:
                activity_subscribers = []
                self.subscribers[activity_type] = activity_subscribers

            if subscriber not in activity_subscribers:
                activity_subscribers.append(subscriber)

    async def handle_publish(self, activity: Activity):
        activity_subscribers = self.subscribers.get(type(activity))
        if activity_subscribers:
            for subscriber in activity_subscribers:
                subscriber.push(activity)

    async def _run(self):
        while True:
            try:
                activity = await asyncio.wait_for(
                    self.activity_queue.get(),
                    timeout=self.inactivity_timeout,
                )
                await self.handle_publish(activity)

            except TimeoutError:
                await self.handle_publish(Inactivity())


class KeyboardMouseActivityPushPublisher(ActivityPushPublisher):
    def __init__(
        self,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        inactivity_timeout: int = DEFAULT_INACTIVITY_TIMEOUT,
    ):
        super().__init__(queue_size, inactivity_timeout)
        self.event_loop = asyncio.get_running_loop()

        self.keyboard_listener: KeyboardListener = KeyboardListener(
            on_press=self._on_key_press
        )
        self.mouse_listener: MouseListener = MouseListener(on_click=self._on_click)
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def _put_activity(self, activity: Activity):
        try:
            self.activity_queue.put_nowait(activity)
        except asyncio.QueueFull:
            self.dropped += 1

    def _on_key_press(self, key):
        timestamp = datetime.now(UTC)
        monotonic_timestamp = time.monotonic()
        self.event_loop.call_soon_threadsafe(
            self._handle_on_key_press,
            key,
            timestamp,
            monotonic_timestamp,
        )

    def _handle_on_key_press(
        self,
        key,
        timestamp: datetime | None = None,
        monotonic_timestamp: float | None = None,
    ):
        if timestamp is None:
            timestamp = datetime.now(UTC)
        if monotonic_timestamp is None:
            monotonic_timestamp = time.monotonic()
        self._put_activity(
            KeyboardActivity(
                key,
                timestamp=timestamp,
                monotonic_timestamp=monotonic_timestamp,
            )
        )

    def _on_click(self, x, y, button, pressed):
        if pressed:
            timestamp = datetime.now(UTC)
            monotonic_timestamp = time.monotonic()
            self.event_loop.call_soon_threadsafe(
                self._handle_on_click,
                x,
                y,
                button,
                pressed,
                timestamp,
                monotonic_timestamp,
            )

    def _handle_on_click(
        self,
        x,
        y,
        button,
        pressed,
        timestamp: datetime | None = None,
        monotonic_timestamp: float | None = None,
    ):
        if pressed:
            if timestamp is None:
                timestamp = datetime.now(UTC)
            if monotonic_timestamp is None:
                monotonic_timestamp = time.monotonic()
            self.last_activity = monotonic_timestamp
            self._put_activity(
                MouseActivity(
                    x,
                    y,
                    button,
                    pressed,
                    timestamp=timestamp,
                    monotonic_timestamp=monotonic_timestamp,
                )
            )

    async def handle_publish(self, activity: Activity):
        await super().handle_publish(activity)

    async def cleanup(self):
        self.keyboard_listener.stop()
        self.mouse_listener.stop()
        try:
            await asyncio.gather(
                asyncio.to_thread(self.keyboard_listener.join),
                asyncio.to_thread(self.mouse_listener.join),
            )
        finally:
            await super().cleanup()
