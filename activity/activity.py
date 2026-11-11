import time
from abc import ABC
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button


@dataclass
class Activity(ABC):
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC), kw_only=True
    )
    monotonic_timestamp: float = field(default_factory=time.monotonic, kw_only=True)


@dataclass
class KeyboardActivity(Activity):
    key: Key | KeyCode


@dataclass
class MouseActivity(Activity):
    x: int
    y: int
    button: Button
    pressed: bool


@dataclass
class Inactivity(Activity):
    pass
