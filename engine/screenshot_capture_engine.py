import asyncio
import math
import time
from datetime import datetime
from pathlib import Path

from mss import mss
from mss.tools import to_png
from pynput.keyboard import Key
from pynput.mouse import Button

from activity.activity import Activity, Inactivity, KeyboardActivity, MouseActivity
from activity.activity_push_subscriber import ActivityPushSubscriber
from util.persistent_object import PersistentImage

DEFAULT_MIN_CAPTURE_FREQUENCY = 0.1
DEFAULT_MAX_CAPTURE_FREQUENCY = 1.0
DEFAULT_RAMP_DOWN_RATE = 0.5
DEFAULT_SCREENSHOT_BASE_DIRECTORY = Path(__file__).resolve().parent.parent


class ScreenshotCaptureEngine(ActivityPushSubscriber):
    def __init__(
        self,
        min_capture_frequency: float = DEFAULT_MIN_CAPTURE_FREQUENCY,
        max_capture_frequency: float = DEFAULT_MAX_CAPTURE_FREQUENCY,
        ramp_down_rate: float = DEFAULT_RAMP_DOWN_RATE,
        screenshot_base_directory: str | Path | None = None,
        *,
        persistent_image_queue: asyncio.Queue[PersistentImage],
    ):
        super().__init__()
        self.persistent_image_queue = persistent_image_queue
        self.min_capture_period = 1 / max_capture_frequency
        self.max_capture_period = 1 / min_capture_frequency
        self.period_ramp_down_rate = 1 / ramp_down_rate

        self.screenshot_base_directory = (
            Path(screenshot_base_directory).expanduser().resolve()
            if screenshot_base_directory is not None
            else DEFAULT_SCREENSHOT_BASE_DIRECTORY
        )
        self.screenshots_directory = (
            self.screenshot_base_directory / "screenshots" / str(id(self))
        )
        self.screenshots_directory.mkdir(parents=True, exist_ok=True)

        self.sct = mss()

        self.last_activity: float = time.monotonic()
        self.last_capture: float = time.monotonic()
        self.capture_period: float = 5
        self.is_active: bool = False
        self.capture_signal = asyncio.Event()

        self.last_mouse_activity: MouseActivity = MouseActivity(
            0, 0, Button.unknown, False
        )
        self.last_keyboard_activity: KeyboardActivity = KeyboardActivity(Key.space)

        self._capture_task = asyncio.create_task(self._capture_worker())

    async def handle_push(self, activity: Activity):
        if isinstance(activity, Inactivity):
            self.is_active = False

        else:
            self.is_active = True
            curr_activity = activity.monotonic_timestamp
            activity_delta = curr_activity - self.last_activity
            new_capture_period = min(
                self.max_capture_period,
                max(self.min_capture_period, activity_delta),
            )
            self.last_activity = curr_activity
            if type(activity) is MouseActivity:
                self.last_mouse_activity = activity
            elif type(activity) is KeyboardActivity:
                self.last_keyboard_activity = activity

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
                    self.max_capture_period,
                    self.capture_period * self.period_ramp_down_rate,
                )
                self.last_capture = time.monotonic()
                persistent_image = await asyncio.to_thread(self._capture)
                await self.persistent_image_queue.put(persistent_image)

    def _capture(self) -> PersistentImage:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = self.screenshots_directory / f"{timestamp}.png"

        x = self.last_mouse_activity.x
        y = self.last_mouse_activity.y
        monitor = next(
            (
                monitor
                for monitor in self.sct.monitors[1:]
                if monitor["left"] <= x < monitor["left"] + monitor["width"]
                and monitor["top"] <= y < monitor["top"] + monitor["height"]
            ),
            self.sct.primary_monitor,
        )

        image = self.sct.grab(monitor)

        to_png(
            image.rgb,
            image.size,
            output=str(filename),
        )
        return PersistentImage(filename)

    async def cleanup(self):
        await super().cleanup()
        self.sct.close()
        self._capture_task.cancel()
        try:
            await self._capture_task
        except asyncio.CancelledError:
            pass
