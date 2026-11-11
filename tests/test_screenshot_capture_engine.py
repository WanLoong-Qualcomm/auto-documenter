import asyncio
import inspect
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from activity.activity import Activity, Inactivity, MouseActivity
from engine.screenshot_capture_engine import ScreenshotCaptureEngine


class ScreenshotCaptureEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.screenshot_base_directory = Path(self.temporary_directory.name)
        self.capture_source = Mock()
        self.capture_source.monitors = [
            {"left": -1280, "top": 0, "width": 5760, "height": 1440},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 2560, "height": 1440},
            {"left": -1280, "top": 0, "width": 1280, "height": 1024},
        ]
        self.capture_source.primary_monitor = self.capture_source.monitors[1]
        self.capture_source.grab.return_value = SimpleNamespace(
            rgb=b"synthetic-rgb", size=(2, 3)
        )
        self.persistent_image_queue = asyncio.Queue(maxsize=1)
        with patch(
            "engine.screenshot_capture_engine.mss", return_value=self.capture_source
        ):
            self.engine = ScreenshotCaptureEngine(
                min_capture_frequency=0.25,
                max_capture_frequency=2,
                screenshot_base_directory=self.screenshot_base_directory,
                persistent_image_queue=self.persistent_image_queue,
            )
        self.cleaned = False

    async def asyncTearDown(self):
        if not self.cleaned:
            await self.engine.cleanup()
        self.temporary_directory.cleanup()

    @staticmethod
    def write_synthetic_png(_rgb, _size, output):
        Path(output).write_bytes(b"synthetic-png")

    async def test_constructor_converts_frequencies_to_periods(self):
        self.assertEqual(self.engine.min_capture_period, 0.5)
        self.assertEqual(self.engine.max_capture_period, 4)
        self.assertEqual(self.engine.capture_period, 5)
        self.assertFalse(self.engine.is_active)
        self.assertIsInstance(self.engine.capture_signal, asyncio.Event)
        self.assertEqual(
            self.engine.screenshot_base_directory, self.screenshot_base_directory
        )
        self.assertEqual(
            self.engine.screenshots_directory,
            self.screenshot_base_directory / "screenshots" / str(id(self.engine)),
        )
        self.assertIs(self.engine.persistent_image_queue, self.persistent_image_queue)
        self.assertTrue(self.engine.screenshots_directory.is_dir())

    async def test_default_base_directory_is_the_application_directory(self):
        temporary_base_directory = Path(self.temporary_directory.name) / "app"
        with patch(
            "engine.screenshot_capture_engine.DEFAULT_SCREENSHOT_BASE_DIRECTORY",
            temporary_base_directory,
        ), patch(
            "engine.screenshot_capture_engine.mss", return_value=Mock()
        ):
            engine = ScreenshotCaptureEngine(
                persistent_image_queue=asyncio.Queue()
            )

        try:
            self.assertEqual(engine.screenshot_base_directory, temporary_base_directory)
            self.assertTrue(engine.screenshots_directory.is_dir())
        finally:
            await engine.cleanup()

    async def test_handle_push_marks_inactivity(self):
        self.engine.is_active = True

        await self.engine.handle_push(Inactivity())

        self.assertFalse(self.engine.is_active)

    async def test_handle_push_clamps_period_and_signals_worker(self):
        self.engine.last_activity = 0

        await self.engine.handle_push(
            Activity(monotonic_timestamp=10)
        )

        self.assertTrue(self.engine.is_active)
        self.assertEqual(self.engine.last_activity, 10)
        self.assertEqual(self.engine.capture_period, self.engine.max_capture_period)
        self.assertTrue(self.engine.capture_signal.is_set())

        self.engine.capture_signal.clear()
        self.engine.last_activity = 19.75
        await self.engine.handle_push(
            Activity(monotonic_timestamp=20)
        )

        self.assertEqual(self.engine.capture_period, self.engine.min_capture_period)
        self.assertTrue(self.engine.capture_signal.is_set())

    async def test_handle_push_does_not_signal_for_nearly_unchanged_period(self):
        self.engine.last_activity = 10
        self.engine.capture_period = 2

        with patch("engine.screenshot_capture_engine.time.monotonic", return_value=100):
            await self.engine.handle_push(
                Activity(monotonic_timestamp=11.95)
            )

        self.assertEqual(self.engine.last_activity, 11.95)
        self.assertEqual(self.engine.capture_period, 2)
        self.assertFalse(self.engine.capture_signal.is_set())

    async def test_capture_worker_doubles_period_then_captures_on_timeout(self):
        self.engine._capture_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.engine._capture_task

        self.engine.capture_period = 1
        self.engine.max_capture_period = 3
        self.engine.last_capture = 0
        self.engine.is_active = True
        wait_calls = 0

        async def timeout_once_then_cancel(awaitable, timeout):
            nonlocal wait_calls
            wait_calls += 1
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            if wait_calls == 1:
                raise TimeoutError
            raise asyncio.CancelledError

        captured_image = object()
        capture_thread = AsyncMock(return_value=captured_image)
        with (
            patch(
                "engine.screenshot_capture_engine.asyncio.wait_for",
                timeout_once_then_cancel,
            ),
            patch(
                "engine.screenshot_capture_engine.asyncio.to_thread",
                capture_thread,
            ),
            patch("engine.screenshot_capture_engine.time.monotonic", return_value=10),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.engine._capture_worker()

        self.assertEqual(wait_calls, 2)
        self.assertEqual(self.engine.capture_period, 2)
        self.assertEqual(self.engine.last_capture, 10)
        capture_thread.assert_awaited_once_with(self.engine._capture)
        self.assertIs(await self.persistent_image_queue.get(), captured_image)

    async def test_capture_worker_waits_for_queue_space(self):
        queued_image = object()
        captured_image = object()
        await self.persistent_image_queue.put(queued_image)
        self.engine.capture_period = 1
        self.engine.last_capture = 0
        self.engine.is_active = True
        wait_calls = 0

        async def timeout_once_then_cancel(awaitable, timeout):
            nonlocal wait_calls
            wait_calls += 1
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            if wait_calls == 1:
                raise TimeoutError
            raise asyncio.CancelledError

        async def return_captured_image(_capture):
            return captured_image

        with (
            patch(
                "engine.screenshot_capture_engine.asyncio.wait_for",
                timeout_once_then_cancel,
            ),
            patch(
                "engine.screenshot_capture_engine.asyncio.to_thread",
                AsyncMock(side_effect=return_captured_image),
            ),
        ):
            worker = asyncio.create_task(self.engine._capture_worker())
            await asyncio.sleep(0)

            self.assertFalse(worker.done())
            self.assertEqual(self.persistent_image_queue.qsize(), 1)
            self.assertIs(await self.persistent_image_queue.get(), queued_image)

            with self.assertRaises(asyncio.CancelledError):
                await worker

        self.assertIs(await self.persistent_image_queue.get(), captured_image)

    async def test_capture_worker_clears_signal_and_restarts_wait(self):
        self.engine._capture_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.engine._capture_task

        self.engine.capture_signal.set()
        actual_wait_for = asyncio.wait_for
        wait_calls = 0

        async def return_signal_then_cancel(awaitable, timeout):
            nonlocal wait_calls
            wait_calls += 1
            if wait_calls == 1:
                return await actual_wait_for(awaitable, timeout)
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise asyncio.CancelledError

        with patch(
            "engine.screenshot_capture_engine.asyncio.wait_for",
            return_signal_then_cancel,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.engine._capture_worker()

        self.assertEqual(wait_calls, 2)
        self.assertFalse(self.engine.capture_signal.is_set())

    async def test_capture_writes_png_from_primary_monitor(self):
        fixed_datetime = Mock()
        fixed_datetime.strftime.return_value = "20250102_030405_123456"
        with (
            patch("engine.screenshot_capture_engine.datetime") as datetime_class,
            patch("engine.screenshot_capture_engine.to_png") as to_png,
        ):
            datetime_class.now.return_value = fixed_datetime
            to_png.side_effect = self.write_synthetic_png

            captured_image = self.engine._capture()

        self.capture_source.grab.assert_called_once_with(
            self.capture_source.monitors[1]
        )
        to_png.assert_called_once_with(
            b"synthetic-rgb",
            (2, 3),
            output=str(
                self.engine.screenshots_directory / "20250102_030405_123456.png"
            ),
        )
        captured_image_path = captured_image.path
        self.assertTrue(captured_image_path.is_file())
        self.assertTrue(self.engine.screenshots_directory.is_dir())
        captured_image.release()
        self.assertFalse(captured_image_path.exists())

    async def test_capture_selects_monitor_containing_last_mouse_position(self):
        self.engine.last_mouse_activity = MouseActivity(
            -640, 500, object(), True
        )
        fixed_datetime = Mock()
        fixed_datetime.strftime.return_value = "20250102_030405_123456"
        with (
            patch("engine.screenshot_capture_engine.datetime") as datetime_class,
            patch("engine.screenshot_capture_engine.to_png") as to_png,
        ):
            datetime_class.now.return_value = fixed_datetime
            to_png.side_effect = self.write_synthetic_png

            self.engine._capture()

        self.capture_source.grab.assert_called_once_with(
            self.capture_source.monitors[3]
        )

    async def test_capture_smoke_encodes_synthetic_screenshot_from_dict_monitor(self):
        mouse_activity = MouseActivity(-640, 500, object(), True)
        with patch("engine.screenshot_capture_engine.time.monotonic", return_value=1):
            await self.engine.handle_push(mouse_activity)

        self.assertIs(self.engine.last_mouse_activity, mouse_activity)
        self.capture_source.grab.return_value = SimpleNamespace(
            rgb=bytes(2 * 3 * 3), size=(2, 3)
        )
        captured_image = self.engine._capture()

        screenshot_path = next(self.engine.screenshots_directory.glob("*.png"))
        self.assertEqual(screenshot_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.capture_source.grab.assert_called_once_with(self.capture_source.monitors[3])
        image = captured_image.get_image()
        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (2, 3))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))

    async def test_capture_falls_back_to_primary_for_off_screen_position(self):
        self.engine.last_mouse_activity = MouseActivity(
            5000, 2000, object(), True
        )
        fixed_datetime = Mock()
        fixed_datetime.strftime.return_value = "20250102_030405_123456"
        with (
            patch("engine.screenshot_capture_engine.datetime") as datetime_class,
            patch("engine.screenshot_capture_engine.to_png") as to_png,
        ):
            datetime_class.now.return_value = fixed_datetime
            to_png.side_effect = self.write_synthetic_png

            self.engine._capture()

        self.capture_source.grab.assert_called_once_with(
            self.capture_source.primary_monitor
        )

    async def test_each_engine_gets_a_distinct_session_directory(self):
        second_capture_source = Mock()
        second_capture_source.monitors = self.capture_source.monitors
        second_capture_source.primary_monitor = self.capture_source.primary_monitor
        with patch(
            "engine.screenshot_capture_engine.mss", return_value=second_capture_source
        ):
            second_engine = ScreenshotCaptureEngine(
                screenshot_base_directory=self.screenshot_base_directory,
                persistent_image_queue=asyncio.Queue(),
            )

        try:
            self.assertNotEqual(
                self.engine.screenshots_directory, second_engine.screenshots_directory
            )
            self.assertEqual(
                second_engine.screenshots_directory.name, str(id(second_engine))
            )
            self.assertTrue(second_engine.screenshots_directory.is_dir())
        finally:
            await second_engine.cleanup()

    async def test_multiple_captures_write_into_same_session_directory(self):
        fixed_datetimes = [
            Mock(strftime=Mock(return_value="20250102_030405_000001")),
            Mock(strftime=Mock(return_value="20250102_030405_000002")),
        ]
        with (
            patch(
                "engine.screenshot_capture_engine.datetime"
            ) as datetime_class,
            patch("engine.screenshot_capture_engine.to_png") as to_png,
        ):
            datetime_class.now.side_effect = fixed_datetimes
            to_png.side_effect = self.write_synthetic_png

            self.engine._capture()
            self.engine._capture()

        output_directories = {
            Path(call.kwargs["output"]).parent for call in to_png.call_args_list
        }
        self.assertEqual(output_directories, {self.engine.screenshots_directory})
        self.assertEqual(to_png.call_count, 2)

    async def test_cleanup_closes_capture_source_and_cancels_workers(self):
        await self.engine.cleanup()
        self.cleaned = True

        self.capture_source.close.assert_called_once_with()
        self.assertTrue(self.engine._run_task.cancelled())
        self.assertTrue(self.engine._capture_task.cancelled())

