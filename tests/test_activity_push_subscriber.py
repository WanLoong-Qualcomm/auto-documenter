import asyncio
import inspect
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from activity.activity import Activity
from activity.activity_push_subscriber import ActivityPushSubscriber


class RecordingSubscriber(ActivityPushSubscriber):
    def __init__(self, **kwargs):
        self.received = []
        self.received_event = asyncio.Event()
        super().__init__(**kwargs)

    async def handle_push(self, activity):
        self.received.append(activity)
        self.received_event.set()


class ActivityPushSubscriberTests(unittest.IsolatedAsyncioTestCase):
    async def test_push_queues_and_dispatches_activity(self):
        subscriber = RecordingSubscriber(queue_size=1)
        activity = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        try:
            subscriber.push(activity)
            subscriber.push(Activity(timestamp=datetime(2025, 1, 3, tzinfo=UTC)))

            await asyncio.wait_for(subscriber.received_event.wait(), timeout=1)

            self.assertEqual(subscriber.received, [activity])
            self.assertEqual(subscriber.dropped, 1)
        finally:
            await subscriber.cleanup()

    async def test_run_continues_after_queue_timeout(self):
        subscriber = RecordingSubscriber(inactivity_timeout=0.01)
        calls = 0

        async def timeout_once_then_cancel(awaitable, timeout):
            nonlocal calls
            calls += 1
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            if calls == 1:
                raise TimeoutError
            raise asyncio.CancelledError

        try:
            with patch(
                "activity.activity_push_subscriber.asyncio.wait_for",
                timeout_once_then_cancel,
            ):
                await asyncio.sleep(0)

            with self.assertRaises(asyncio.CancelledError):
                await subscriber._run_task

            self.assertEqual(calls, 2)
            self.assertEqual(subscriber.received, [])
        finally:
            await subscriber.cleanup()

    async def test_handle_push_remains_an_abstract_contract(self):
        with self.assertRaises(TypeError):
            ActivityPushSubscriber()

