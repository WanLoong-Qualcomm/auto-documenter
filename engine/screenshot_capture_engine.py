import asyncio
import math
import time
from datetime import datetime
from pathlib import Path

from mss import mss
from mss.tools import to_png

from activity.activity import Activity, Inactivity
from activity.activity_push_subscriber import ActivityPushSubscriber


class ScreenshotCaptureEngine(ActivityPushSubscriber):
    def __init__(
        self, min_capture_frequency: float = 0.1, max_capture_frequency: float = 1
    ):
        super().__init__()
        self.min_capture_period = 1 / max_capture_frequency
        self.max_capture_period = 1 / min_capture_frequency

        self.sct = mss()

        self.last_activity: float = time.monotonic()
        self.last_capture: float = time.monotonic()
        self.capture_period: float = 5
        self.is_active: bool = False
        self.capture_signal = asyncio.Event()

        self._capture_task = asyncio.create_task(self._capture_worker())

    async def handle_push(self, activity: Activity):
        if isinstance(activity, Inactivity):
            self.is_active = False

        else:
            self.is_active = True
            curr_activity = time.monotonic()
            activity_delta = curr_activity - self.last_activity
            new_capture_period = min(
                self.max_capture_period,
                max(self.min_capture_period, activity_delta),
            )
            self.last_activity = curr_activity
            if math.isclose(new_capture_period, self.capture_period, abs_tol=0.1):
                return

            self.capture_period = new_capture_period
            self.capture_signal.set()

    async def _capture_worker(self):
        while True:
            elapsed = time.monotonic() - self.last_capture
            remaining = max(0, self.capture_period - elapsed)

            try:
                await asyncio.wait_for(
                    self.capture_signal.wait(),
                    timeout=remaining,
                )
                self.capture_signal.clear()
                continue

            except TimeoutError:
                pass

            if self.is_active:
                # NOTE Hardcoded ramp rate
                self.capture_period = min(
                    self.max_capture_period, self.capture_period * 2
                )
                self.last_capture = time.monotonic()
                await asyncio.to_thread(self._capture)

    def _capture(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = screenshots_dir / f"{timestamp}.png"

        monitor = self.sct.monitors[1]  # monitor 0 = virtual desktop

        image = self.sct.grab(monitor)

        to_png(
            image.rgb,
            image.size,
            output=str(filename),
        )

    async def cleanup(self):
        await super().cleanup()
        self.sct.close()
        self._capture_task.cancel()
        try:
            await self._capture_task
        except asyncio.CancelledError:
            pass
