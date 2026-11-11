import time
import unittest
from datetime import UTC, datetime

from activity.activity import Activity, Inactivity, KeyboardActivity, MouseActivity


class ActivityModelTests(unittest.TestCase):
    def test_activity_retains_timestamp(self):
        timestamp = datetime(2025, 1, 2, tzinfo=UTC)

        activity = Activity(timestamp=timestamp, monotonic_timestamp=12.5)

        self.assertEqual(activity.timestamp, timestamp)
        self.assertEqual(activity.monotonic_timestamp, 12.5)

    def test_monotonic_timestamp_defaults_to_creation_time(self):
        before_creation = time.monotonic()

        activity = Activity()

        after_creation = time.monotonic()
        self.assertLessEqual(before_creation, activity.monotonic_timestamp)
        self.assertLessEqual(activity.monotonic_timestamp, after_creation)

    def test_timestamp_defaults_to_utc_creation_time(self):
        before_creation = datetime.now(UTC)

        activity = Activity()

        after_creation = datetime.now(UTC)
        self.assertIs(activity.timestamp.tzinfo, UTC)
        self.assertLessEqual(before_creation, activity.timestamp)
        self.assertLessEqual(activity.timestamp, after_creation)

    def test_keyboard_activity_retains_timestamp_and_key(self):
        timestamp = datetime(2025, 1, 2, tzinfo=UTC)
        key = object()

        activity = KeyboardActivity(key, timestamp=timestamp)

        self.assertEqual(activity.timestamp, timestamp)
        self.assertIs(activity.key, key)

    def test_mouse_activity_retains_event_fields(self):
        timestamp = datetime(2025, 1, 2, tzinfo=UTC)
        button = object()

        activity = MouseActivity(12, 34, button, True, timestamp=timestamp)

        self.assertEqual(activity.timestamp, timestamp)
        self.assertEqual((activity.x, activity.y), (12, 34))
        self.assertIs(activity.button, button)
        self.assertTrue(activity.pressed)

    def test_inactivity_retains_timestamp(self):
        timestamp = datetime(2025, 1, 2, tzinfo=UTC)

        activity = Inactivity(timestamp=timestamp)

        self.assertEqual(activity.timestamp, timestamp)

