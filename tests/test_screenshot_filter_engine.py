import asyncio
import tempfile
import unittest
from pathlib import Path

from PIL import Image as PillowImage, ImageDraw

from engine.screenshot_filter_engine import ScreenshotFilterEngine
from util.persistent_object import PersistentImage


class ScreenshotFilterEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()
        self.engine = ScreenshotFilterEngine(self.input_queue, self.output_queue)
        self.image_number = 0

    async def asyncTearDown(self):
        await self.engine.cleanup()
        self.temporary_directory.cleanup()

    def create_image(self, color, changed_pixel=None):
        image_path = Path(self.temporary_directory.name) / f"{self.image_number}.png"
        self.image_number += 1

        image = PillowImage.new("RGB", (128, 72), color)
        if changed_pixel is not None:
            image.putpixel(changed_pixel, (0, 0, 0))
        image.save(image_path)
        image.close()
        return PersistentImage(image_path)

    async def test_forwards_first_image_and_releases_a_similar_image(self):
        first_image = self.create_image((0, 0, 0))
        similar_image = self.create_image((0, 0, 0), changed_pixel=(0, 0))
        similar_image_path = similar_image.path

        await self.input_queue.put(first_image)
        await self.input_queue.put(similar_image)
        await asyncio.wait_for(self.input_queue.join(), timeout=1)

        self.assertIs(await self.output_queue.get(), first_image)
        self.assertFalse(similar_image_path.exists())

    async def test_updates_reference_when_forwarding_a_different_image(self):
        first_image = self.create_image((0, 0, 0))
        different_image = self.create_image((255, 255, 255))
        similar_to_latest = self.create_image(
            (255, 255, 255), changed_pixel=(0, 0)
        )
        similar_to_latest_path = similar_to_latest.path

        await self.input_queue.put(first_image)
        await self.input_queue.put(different_image)
        await self.input_queue.put(similar_to_latest)
        await asyncio.wait_for(self.input_queue.join(), timeout=1)

        self.assertIs(await self.output_queue.get(), first_image)
        self.assertIs(await self.output_queue.get(), different_image)
        self.assertEqual(self.output_queue.qsize(), 0)
        self.assertFalse(similar_to_latest_path.exists())

    async def test_forwards_image_with_a_small_structural_change(self):
        first_image = self.create_image((0, 0, 0))
        changed_image_path = Path(self.temporary_directory.name) / "local-change.png"
        changed_image = PillowImage.new("RGB", (128, 72), "black")
        ImageDraw.Draw(changed_image).rectangle((60, 32, 64, 36), fill="white")
        changed_image.save(changed_image_path)
        changed_image.close()
        changed_image = PersistentImage(changed_image_path)

        await self.input_queue.put(first_image)
        await self.input_queue.put(changed_image)
        await asyncio.wait_for(self.input_queue.join(), timeout=1)

        self.assertIs(await self.output_queue.get(), first_image)
        self.assertIs(await self.output_queue.get(), changed_image)

    async def test_rejects_similarity_threshold_outside_zero_to_one(self):
        with self.assertRaises(ValueError):
            ScreenshotFilterEngine(self.input_queue, self.output_queue, 1.1)

    async def test_uses_configured_comparison_size(self):
        comparison_size = (64, 36)
        engine = ScreenshotFilterEngine(
            asyncio.Queue(),
            asyncio.Queue(),
            comparison_size=comparison_size,
            ssim_window_size=5,
            ssim_sigma=1.0,
        )
        input_image = self.create_image((10, 20, 30))

        try:
            await engine.input_queue.put(input_image)
            await asyncio.wait_for(engine.input_queue.join(), timeout=1)

            self.assertEqual(engine._last_output_thumbnail.size, comparison_size)
            self.assertEqual(engine.ssim_window_size, 5)
            self.assertEqual(engine.ssim_sigma, 1.0)
        finally:
            await engine.cleanup()

    async def test_rejects_invalid_comparison_size(self):
        with self.assertRaises(ValueError):
            ScreenshotFilterEngine(
                self.input_queue, self.output_queue, comparison_size=(0, 72)
            )

    async def test_rejects_comparison_size_smaller_than_ssim_window(self):
        with self.assertRaises(ValueError):
            ScreenshotFilterEngine(
                self.input_queue, self.output_queue, comparison_size=(8, 8)
            )

    async def test_rejects_invalid_ssim_window_size(self):
        with self.assertRaises(ValueError):
            ScreenshotFilterEngine(
                self.input_queue, self.output_queue, ssim_window_size=10
            )

    def test_ssim_is_one_for_identical_images(self):
        image = PillowImage.new("RGB", (128, 72), (24, 80, 160))
        copy = image.copy()

        try:
            self.assertAlmostEqual(
                self.engine._similarity(image, copy), 1.0, places=12
            )
        finally:
            image.close()
            copy.close()

    def test_ssim_detects_a_small_structural_change(self):
        original = PillowImage.new("RGB", (128, 72), "black")
        changed = original.copy()
        ImageDraw.Draw(changed).rectangle((60, 32, 64, 36), fill="white")

        try:
            similarity = self.engine._similarity(original, changed)

            self.assertLess(similarity, self.engine.similarity_threshold)
        finally:
            original.close()
            changed.close()
