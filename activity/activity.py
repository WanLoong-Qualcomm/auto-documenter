from abc import ABC
from dataclasses import dataclass
from datetime import datetime

from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button


@dataclass
class Activity(ABC):
    timestamp: datetime


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
