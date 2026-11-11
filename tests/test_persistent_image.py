import tempfile
import unittest
from pathlib import Path

from PIL import Image as PillowImage

from exception import ReleasedException
from util.persistent_object import PersistentImage


class PersistentImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.image_path = Path(self.temporary_directory.name) / "synthetic.png"
        PillowImage.new("RGB", (2, 3), (12, 34, 56)).save(self.image_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_get_image_returns_a_detached_pillow_image(self):
        persistent_image = PersistentImage(self.image_path)

        image = persistent_image.get_image()

        self.assertIsInstance(image, PillowImage.Image)
        self.assertEqual(image.size, (2, 3))
        self.assertEqual(image.getpixel((0, 0)), (12, 34, 56))

    def test_release_deletes_file_and_disables_access(self):
        persistent_image = PersistentImage(self.image_path)
        image = persistent_image.get_image()

        persistent_image.release()

        self.assertFalse(self.image_path.exists())
        self.assertEqual(image.getpixel((0, 0)), (12, 34, 56))
        with self.assertRaises(ReleasedException):
            persistent_image.get_image()

        with self.assertRaises(ReleasedException):
            persistent_image.release()
        self.assertFalse(self.image_path.exists())

    def test_constructor_requires_an_existing_image_file(self):
        missing_path = Path(self.temporary_directory.name) / "missing.png"

        with self.assertRaises(FileNotFoundError):
            PersistentImage(missing_path)
