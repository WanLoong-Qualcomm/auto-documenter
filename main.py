import asyncio

from activity.activity import Activity
from activity.activity_push_publisher import KeyboardMouseActivityPushPublisher
from engine.screenshot_capture_engine import ScreenshotCaptureEngine

INACTIVITY_TIMEOUT = 10


async def main():
    publisher = None
    screenshot_engine = None

    try:
        publisher = KeyboardMouseActivityPushPublisher(
            inactivity_timeout=INACTIVITY_TIMEOUT
        )
        screenshot_engine = ScreenshotCaptureEngine(
            min_capture_frequency=2 / INACTIVITY_TIMEOUT,
            max_capture_frequency=10 / INACTIVITY_TIMEOUT,
        )
        publisher.subscribe(screenshot_engine, [Activity])
        await asyncio.to_thread(input, "Press Enter to close the application.")
    finally:
        try:
            if publisher is not None:
                await publisher.cleanup()
        finally:
            if screenshot_engine is not None:
                await screenshot_engine.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
