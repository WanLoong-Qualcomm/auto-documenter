import asyncio
import unittest

from activity.activity_base import AsyncActivityBase


class BlockingActivity(AsyncActivityBase):
    def __init__(self, **kwargs):
        self.stopped = asyncio.Event()
        super().__init__(**kwargs)

    async def _run(self):
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()


class AsyncActivityBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_configures_queue_and_counters(self):
        activity = BlockingActivity(queue_size=3, inactivity_timeout=7)
        try:
            self.assertEqual(activity.activity_queue.maxsize, 3)
            self.assertEqual(activity.inactivity_timeout, 7)
            self.assertEqual(activity.dropped, 0)
            self.assertFalse(activity._run_task.done())
        finally:
            await activity.cleanup()

    async def test_cleanup_cancels_run_task(self):
        activity = BlockingActivity()
        await asyncio.sleep(0)

        await activity.cleanup()

        self.assertTrue(activity._run_task.cancelled())
        self.assertTrue(activity.stopped.is_set())

    async def test_run_must_be_implemented(self):
        with self.assertRaises(TypeError):
            AsyncActivityBase()

