import argparse
import asyncio
from pathlib import Path

from activity.activity import Inactivity, KeyboardActivity, MouseActivity
from activity.activity_push_publisher import KeyboardMouseActivityPushPublisher
from engine.screenshot_capture_engine import ScreenshotCaptureEngine
from engine.screenshot_filter_engine import ScreenshotFilterEngine
from util.persistent_object import PersistentImage

INACTIVITY_TIMEOUT = 10


async def main(screenshot_base_directory: str | Path | None = None):
    publisher = None
    screenshot_engine = None
    screenshot_filter_engine = None
    persistent_image_queue: asyncio.Queue[PersistentImage] = asyncio.Queue(maxsize=1000)
    persistent_filtered_image_queue: asyncio.Queue[PersistentImage] = asyncio.Queue(
        maxsize=1000
    )

    try:
        publisher = KeyboardMouseActivityPushPublisher(
            inactivity_timeout=INACTIVITY_TIMEOUT
        )
        screenshot_engine = ScreenshotCaptureEngine(
            min_capture_frequency=2 / INACTIVITY_TIMEOUT,
            max_capture_frequency=20 / INACTIVITY_TIMEOUT,
            screenshot_base_directory=screenshot_base_directory,
            persistent_image_queue=persistent_image_queue,
        )
        screenshot_filter_engine = ScreenshotFilterEngine(
            persistent_image_queue,
            persistent_filtered_image_queue,
        )
        publisher.subscribe(
            screenshot_engine,
            [KeyboardActivity, MouseActivity, Inactivity],
        )
        await asyncio.to_thread(input, "Press Enter to close the application.")
    finally:
        try:
            if publisher is not None:
                await publisher.cleanup()
        finally:
            try:
                if screenshot_engine is not None:
                    await screenshot_engine.cleanup()
            finally:
                if screenshot_filter_engine is not None:
                    await screenshot_filter_engine.cleanup()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Capture screenshots during activity.")
    parser.add_argument(
        "--screenshot-base-directory",
        type=Path,
        help="base directory for this session's screenshots",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(screenshot_base_directory=args.screenshot_base_directory))
