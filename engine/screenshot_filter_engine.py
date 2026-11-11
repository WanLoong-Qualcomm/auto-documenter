import asyncio
import math

import numpy as np
from PIL import Image

from util.persistent_object import PersistentImage

DEFAULT_COMPARISON_SIZE = (128, 72)
DEFAULT_SIMILARITY_THRESHOLD = 0.98
DEFAULT_SSIM_WINDOW_SIZE = 11
DEFAULT_SSIM_SIGMA = 1.5
SSIM_K1 = 0.01
SSIM_K2 = 0.03


class ScreenshotFilterEngine:
    def __init__(
        self,
        input_queue: asyncio.Queue[PersistentImage],
        output_queue: asyncio.Queue[PersistentImage],
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        comparison_size: tuple[int, int] = DEFAULT_COMPARISON_SIZE,
        ssim_window_size: int = DEFAULT_SSIM_WINDOW_SIZE,
        ssim_sigma: float = DEFAULT_SSIM_SIGMA,
    ):
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if (
            not isinstance(comparison_size, tuple)
            or len(comparison_size) != 2
            or any(
                type(dimension) is not int or dimension <= 0
                for dimension in comparison_size
            )
        ):
            raise ValueError("comparison_size must contain two positive integers")
        if (
            type(ssim_window_size) is not int
            or ssim_window_size < 3
            or ssim_window_size % 2 == 0
        ):
            raise ValueError("ssim_window_size must be an odd integer of at least 3")
        if (
            comparison_size[0] < ssim_window_size
            or comparison_size[1] < ssim_window_size
        ):
            raise ValueError(
                "comparison_size dimensions must be at least ssim_window_size"
            )
        if not math.isfinite(ssim_sigma) or ssim_sigma <= 0:
            raise ValueError("ssim_sigma must be a positive finite number")

        self.input_queue = input_queue
        self.output_queue = output_queue
        self.similarity_threshold = similarity_threshold
        self.comparison_size = comparison_size
        self.ssim_window_size = ssim_window_size
        self.ssim_sigma = ssim_sigma
        self._last_output_thumbnail: Image.Image | None = None
        self._filter_task = asyncio.create_task(self._filter_images())

    async def _filter_images(self):
        while True:
            persistent_image = await self.input_queue.get()
            thumbnail = None

            try:
                thumbnail = await asyncio.to_thread(
                    self._create_thumbnail, persistent_image, self.comparison_size
                )
                previous_thumbnail = self._last_output_thumbnail
                is_similar = False
                if previous_thumbnail is not None:
                    similarity = await asyncio.to_thread(
                        self._similarity,
                        previous_thumbnail,
                        thumbnail,
                        self.ssim_window_size,
                        self.ssim_sigma,
                    )
                    is_similar = similarity >= self.similarity_threshold

                if is_similar:
                    persistent_image.release()
                else:
                    await self.output_queue.put(persistent_image)
                    self._last_output_thumbnail = thumbnail
                    thumbnail = None
                    if previous_thumbnail is not None:
                        previous_thumbnail.close()
            finally:
                if thumbnail is not None:
                    thumbnail.close()
                self.input_queue.task_done()

    @staticmethod
    def _create_thumbnail(
        persistent_image: PersistentImage, comparison_size: tuple[int, int]
    ) -> Image.Image:
        with persistent_image.get_image() as image, image.convert("RGB") as rgb_image:
            return rgb_image.resize(comparison_size, Image.Resampling.BOX)

    @staticmethod
    def _similarity(
        first: Image.Image,
        second: Image.Image,
        window_size: int = DEFAULT_SSIM_WINDOW_SIZE,
        sigma: float = DEFAULT_SSIM_SIGMA,
    ) -> float:
        """Return the mean Gaussian-windowed SSIM across RGB channels."""
        if first.size != second.size:
            raise ValueError("images must have the same dimensions")
        if first.width < window_size or first.height < window_size:
            raise ValueError("images must be at least as large as the SSIM window")

        with first.convert("RGB") as first_rgb, second.convert("RGB") as second_rgb:
            first_pixels = np.asarray(first_rgb, dtype=np.float64)
            second_pixels = np.asarray(second_rgb, dtype=np.float64)

        coordinates = np.arange(window_size, dtype=np.float64) - (window_size - 1) / 2
        gaussian = np.exp(-(coordinates**2) / (2 * sigma**2))
        gaussian /= gaussian.sum()
        weights = np.outer(gaussian, gaussian)

        first_windows = np.lib.stride_tricks.sliding_window_view(
            first_pixels, (window_size, window_size), axis=(0, 1)
        )
        second_windows = np.lib.stride_tricks.sliding_window_view(
            second_pixels, (window_size, window_size), axis=(0, 1)
        )

        first_mean = np.einsum(
            "ij,xycij->xyc", weights, first_windows, optimize=True
        )
        second_mean = np.einsum(
            "ij,xycij->xyc", weights, second_windows, optimize=True
        )
        first_variance = (
            np.einsum(
                "ij,xycij->xyc", weights, first_windows * first_windows, optimize=True
            )
            - first_mean**2
        )
        second_variance = (
            np.einsum(
                "ij,xycij->xyc",
                weights,
                second_windows * second_windows,
                optimize=True,
            )
            - second_mean**2
        )
        covariance = (
            np.einsum(
                "ij,xycij->xyc",
                weights,
                first_windows * second_windows,
                optimize=True,
            )
            - first_mean * second_mean
        )

        first_variance = np.maximum(first_variance, 0)
        second_variance = np.maximum(second_variance, 0)
        c1 = (SSIM_K1 * 255) ** 2
        c2 = (SSIM_K2 * 255) ** 2
        similarity = (
            (2 * first_mean * second_mean + c1) * (2 * covariance + c2)
        ) / (
            (first_mean**2 + second_mean**2 + c1)
            * (first_variance + second_variance + c2)
        )
        return float(similarity.mean())

    async def cleanup(self):
        self._filter_task.cancel()
        try:
            await self._filter_task
        except asyncio.CancelledError:
            pass
        finally:
            if self._last_output_thumbnail is not None:
                self._last_output_thumbnail.close()
                self._last_output_thumbnail = None
