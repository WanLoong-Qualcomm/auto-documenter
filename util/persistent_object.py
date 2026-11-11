from pathlib import Path

from PIL import Image

from abstract import Releasable
from exception import ReleasedException


class PersistentObject(Releasable):
    def __init__(self):
        self._released: bool = False

    def __getattribute__(self, name):
        if object.__getattribute__(self, "_released"):
            raise ReleasedException()
        return object.__getattribute__(self, name)

    def release(self):
        self._released = True


class PersistentImage(PersistentObject):
    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def get_image(self) -> Image.Image:
        with Image.open(self.path) as image:
            return image.copy()

    def release(self):
        self.path.unlink()
        # Make sure to call super().release() last!
        super().release()
