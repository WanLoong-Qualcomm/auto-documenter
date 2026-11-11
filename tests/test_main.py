import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import main
from activity.activity import Inactivity, KeyboardActivity, MouseActivity


class MainTests(unittest.IsolatedAsyncioTestCase):
    def make_fakes(self):
        cleanup_order = []
        publisher = Mock()
        publisher.cleanup = AsyncMock(side_effect=lambda: cleanup_order.append("publisher"))
        screenshot_engine = Mock()
        screenshot_engine.cleanup = AsyncMock(
            side_effect=lambda: cleanup_order.append("screenshot")
        )
        screenshot_filter_engine = Mock()
        screenshot_filter_engine.cleanup = AsyncMock(
            side_effect=lambda: cleanup_order.append("filter")
        )
        return publisher, screenshot_engine, screenshot_filter_engine, cleanup_order

    async def test_main_wires_components_and_cleans_them_up(self):
        publisher, screenshot_engine, screenshot_filter_engine, cleanup_order = (
            self.make_fakes()
        )
        publisher_factory = Mock(return_value=publisher)
        screenshot_factory = Mock(return_value=screenshot_engine)
        filter_factory = Mock(return_value=screenshot_filter_engine)
        to_thread = AsyncMock(return_value=None)

        with (
            patch.object(main, "KeyboardMouseActivityPushPublisher", publisher_factory),
            patch.object(main, "ScreenshotCaptureEngine", screenshot_factory),
            patch.object(main, "ScreenshotFilterEngine", filter_factory),
            patch.object(main.asyncio, "to_thread", to_thread),
        ):
            await main.main()

        publisher_factory.assert_called_once_with(inactivity_timeout=10)
        screenshot_factory.assert_called_once()
        screenshot_args = screenshot_factory.call_args.kwargs
        self.assertEqual(
            {
                key: value
                for key, value in screenshot_args.items()
                if key != "persistent_image_queue"
            },
            {
                "min_capture_frequency": 0.2,
                "max_capture_frequency": 2.0,
                "screenshot_base_directory": None,
            },
        )
        self.assertIsInstance(
            screenshot_args["persistent_image_queue"], asyncio.Queue
        )
        self.assertEqual(screenshot_args["persistent_image_queue"].maxsize, 1000)
        filter_factory.assert_called_once()
        input_queue, output_queue = filter_factory.call_args.args
        self.assertIs(input_queue, screenshot_args["persistent_image_queue"])
        self.assertIsInstance(output_queue, asyncio.Queue)
        self.assertEqual(output_queue.maxsize, 1000)
        publisher.subscribe.assert_called_once_with(
            screenshot_engine,
            [KeyboardActivity, MouseActivity, Inactivity],
        )
        to_thread.assert_awaited_once_with(
            input, "Press Enter to close the application."
        )
        self.assertEqual(cleanup_order, ["publisher", "screenshot", "filter"])

    async def test_main_passes_custom_screenshot_base_directory(self):
        screenshot_base_directory = Path("custom-captures")
        publisher, screenshot_engine, screenshot_filter_engine, _ = self.make_fakes()
        screenshot_factory = Mock(return_value=screenshot_engine)
        filter_factory = Mock(return_value=screenshot_filter_engine)

        with (
            patch.object(
                main,
                "KeyboardMouseActivityPushPublisher",
                Mock(return_value=publisher),
            ),
            patch.object(main, "ScreenshotCaptureEngine", screenshot_factory),
            patch.object(main, "ScreenshotFilterEngine", filter_factory),
            patch.object(main.asyncio, "to_thread", AsyncMock(return_value=None)),
        ):
            await main.main(screenshot_base_directory=screenshot_base_directory)

        screenshot_factory.assert_called_once()
        screenshot_args = screenshot_factory.call_args.kwargs
        self.assertEqual(
            {
                key: value
                for key, value in screenshot_args.items()
                if key != "persistent_image_queue"
            },
            {
                "min_capture_frequency": 0.2,
                "max_capture_frequency": 2.0,
                "screenshot_base_directory": screenshot_base_directory,
            },
        )
        self.assertIsInstance(screenshot_args["persistent_image_queue"], asyncio.Queue)
        filter_factory.assert_called_once()
        self.assertIs(filter_factory.call_args.args[0], screenshot_args["persistent_image_queue"])

    def test_parse_args_accepts_custom_screenshot_base_directory(self):
        screenshot_base_directory = Path("custom-captures")

        args = main.parse_args(
            ["--screenshot-base-directory", str(screenshot_base_directory)]
        )

        self.assertEqual(args.screenshot_base_directory, screenshot_base_directory)

    async def test_main_cleans_up_when_waiting_for_input_fails(self):
        publisher, screenshot_engine, screenshot_filter_engine, cleanup_order = (
            self.make_fakes()
        )
        error = RuntimeError("input failed")

        with (
            patch.object(
                main,
                "KeyboardMouseActivityPushPublisher",
                Mock(return_value=publisher),
            ),
            patch.object(
                main,
                "ScreenshotCaptureEngine",
                Mock(return_value=screenshot_engine),
            ),
            patch.object(
                main,
                "ScreenshotFilterEngine",
                Mock(return_value=screenshot_filter_engine),
            ),
            patch.object(main.asyncio, "to_thread", AsyncMock(side_effect=error)),
        ):
            with self.assertRaisesRegex(RuntimeError, "input failed"):
                await main.main()

        self.assertEqual(cleanup_order, ["publisher", "screenshot", "filter"])
