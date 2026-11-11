import asyncio
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from activity.activity import Activity, Inactivity, KeyboardActivity
from activity.activity_push_publisher import (
    ActivityPushPublisher,
    KeyboardMouseActivityPushPublisher,
)


class RecordingPushable:
    def __init__(self):
        self.received = []
        self.changed = asyncio.Event()

    def push(self, activity):
        self.received.append(activity)
        self.changed.set()

    async def wait_for_count(self, count):
        while len(self.received) < count:
            self.changed.clear()
            await self.changed.wait()


class ActivityPushPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_accepts_queue_size_and_inactivity_timeout(self):
        publisher = ActivityPushPublisher(queue_size=3, inactivity_timeout=7)
        try:
            self.assertEqual(publisher.activity_queue.maxsize, 3)
            self.assertEqual(publisher.inactivity_timeout, 7)
        finally:
            await publisher.cleanup()

    async def test_subscribe_registers_each_type_once(self):
        publisher = ActivityPushPublisher()
        subscriber = RecordingPushable()
        try:
            publisher.subscribe(subscriber, [Activity, KeyboardActivity])
            publisher.subscribe(subscriber, [Activity])

            self.assertEqual(publisher.subscribers[Activity], [subscriber])
            self.assertEqual(publisher.subscribers[KeyboardActivity], [subscriber])
        finally:
            await publisher.cleanup()

    async def test_handle_publish_sends_to_activity_subscribers(self):
        publisher = ActivityPushPublisher()
        subscriber = RecordingPushable()
        activity = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        publisher.subscribe(subscriber, [Activity])
        try:
            await publisher.handle_publish(activity)

            self.assertEqual(subscriber.received, [activity])
        finally:
            await publisher.cleanup()

    async def test_handle_publish_matches_exact_activity_type(self):
        publisher = ActivityPushPublisher()
        base_subscriber = RecordingPushable()
        keyboard_subscriber = RecordingPushable()
        activity = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        keyboard_activity = KeyboardActivity(
            object(), timestamp=datetime(2025, 1, 3, tzinfo=UTC)
        )
        publisher.subscribe(base_subscriber, [Activity])
        publisher.subscribe(keyboard_subscriber, [KeyboardActivity])
        try:
            await publisher.handle_publish(keyboard_activity)
            await publisher.handle_publish(activity)

            self.assertEqual(base_subscriber.received, [activity])
            self.assertEqual(keyboard_subscriber.received, [keyboard_activity])
        finally:
            await publisher.cleanup()

    async def test_run_publishes_queued_activity_and_inactivity(self):
        publisher = ActivityPushPublisher(inactivity_timeout=0.02)
        subscriber = RecordingPushable()
        activity = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        publisher.subscribe(subscriber, [Activity, Inactivity])
        publisher.activity_queue.put_nowait(activity)
        try:
            await asyncio.wait_for(subscriber.wait_for_count(2), timeout=1)

            self.assertIs(subscriber.received[0], activity)
            self.assertIsInstance(subscriber.received[1], Inactivity)
        finally:
            await publisher.cleanup()


class KeyboardMouseActivityPushPublisherTests(unittest.IsolatedAsyncioTestCase):
    def create_publisher(self, queue_size=10):
        keyboard_listener = Mock()
        mouse_listener = Mock()
        with (
            patch(
                "activity.activity_push_publisher.KeyboardListener",
                return_value=keyboard_listener,
            ) as keyboard_factory,
            patch(
                "activity.activity_push_publisher.MouseListener",
                return_value=mouse_listener,
            ) as mouse_factory,
        ):
            publisher = KeyboardMouseActivityPushPublisher(queue_size=queue_size)
        return (
            publisher,
            keyboard_listener,
            mouse_listener,
            keyboard_factory,
            mouse_factory,
        )

    async def test_constructor_starts_both_listeners(self):
        publisher, keyboard, mouse, keyboard_factory, mouse_factory = (
            self.create_publisher()
        )
        try:
            keyboard_factory.assert_called_once_with(on_press=publisher._on_key_press)
            mouse_factory.assert_called_once_with(on_click=publisher._on_click)
            keyboard.start.assert_called_once_with()
            mouse.start.assert_called_once_with()
        finally:
            await publisher.cleanup()

    async def test_key_callback_schedules_handler_and_handler_queues_event(self):
        publisher, *_ = self.create_publisher()
        publisher.event_loop = Mock()
        key = object()
        try:
            with patch(
                "activity.activity_push_publisher.time.monotonic", return_value=42
            ):
                publisher._on_key_press(key)

            scheduled_call = publisher.event_loop.call_soon_threadsafe.call_args.args
            self.assertEqual(scheduled_call[0], publisher._handle_on_key_press)
            self.assertIs(scheduled_call[1], key)
            self.assertIsInstance(scheduled_call[2], datetime)
            self.assertEqual(scheduled_call[3], 42)
            publisher.event_loop.call_soon_threadsafe.assert_called_once_with(
                *scheduled_call
            )

            publisher._handle_on_key_press(*scheduled_call[1:])
            activity = publisher.activity_queue.get_nowait()
            self.assertIsInstance(activity, KeyboardActivity)
            self.assertIs(activity.key, key)
            self.assertEqual(activity.monotonic_timestamp, 42)
        finally:
            await publisher.cleanup()

    async def test_mouse_callback_schedules_only_pressed_clicks(self):
        publisher, *_ = self.create_publisher()
        publisher.event_loop = Mock()
        button = object()
        try:
            publisher._on_click(1, 2, button, False)
            publisher.event_loop.call_soon_threadsafe.assert_not_called()

            with patch(
                "activity.activity_push_publisher.time.monotonic", return_value=42
            ):
                publisher._on_click(1, 2, button, True)

            scheduled_call = publisher.event_loop.call_soon_threadsafe.call_args.args
            self.assertEqual(scheduled_call[:5], (
                publisher._handle_on_click,
                1,
                2,
                button,
                True,
            ))
            self.assertIsInstance(scheduled_call[5], datetime)
            self.assertEqual(scheduled_call[6], 42)
            publisher.event_loop.call_soon_threadsafe.assert_called_once_with(
                *scheduled_call
            )
        finally:
            await publisher.cleanup()

    async def test_click_handler_queues_press_and_ignores_release(self):
        publisher, *_ = self.create_publisher()
        button = object()
        try:
            publisher._handle_on_click(1, 2, button, False)
            self.assertEqual(publisher.activity_queue.qsize(), 0)
            self.assertFalse(hasattr(publisher, "last_activity"))

            with patch(
                "activity.activity_push_publisher.time.monotonic", return_value=42
            ):
                publisher._handle_on_click(1, 2, button, True)

            activity = publisher.activity_queue.get_nowait()
            self.assertEqual((activity.x, activity.y), (1, 2))
            self.assertIs(activity.button, button)
            self.assertTrue(activity.pressed)
            self.assertEqual(activity.monotonic_timestamp, 42)
            self.assertEqual(publisher.last_activity, 42)
        finally:
            await publisher.cleanup()

    async def test_put_activity_counts_full_queue_drops(self):
        publisher, *_ = self.create_publisher(queue_size=1)
        first = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        second = Activity(timestamp=datetime(2025, 1, 3, tzinfo=UTC))
        try:
            publisher._put_activity(first)
            publisher._put_activity(second)

            self.assertIs(publisher.activity_queue.get_nowait(), first)
            self.assertEqual(publisher.dropped, 1)
        finally:
            await publisher.cleanup()

    async def test_handle_publish_delegates_to_base_publisher(self):
        publisher, *_ = self.create_publisher()
        subscriber = RecordingPushable()
        activity = Activity(timestamp=datetime(2025, 1, 2, tzinfo=UTC))
        publisher.subscribe(subscriber, [Activity])
        try:
            await publisher.handle_publish(activity)

            self.assertEqual(subscriber.received, [activity])
        finally:
            await publisher.cleanup()

    async def test_cleanup_stops_listeners_joins_them_and_cancels_worker(self):
        publisher, keyboard, mouse, *_ = self.create_publisher()

        await publisher.cleanup()

        keyboard.stop.assert_called_once_with()
        mouse.stop.assert_called_once_with()
        keyboard.join.assert_called_once_with()
        mouse.join.assert_called_once_with()
        self.assertTrue(publisher._run_task.cancelled())

