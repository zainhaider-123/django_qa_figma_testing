from io import BytesIO

from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright


class ScreenshotService:
    """Captures screenshots of live sites using Playwright's sync API."""

    @staticmethod
    def capture(url: str, width: int, height: int, timeout: int = 30000) -> bytes:
        """Take a screenshot of a URL at given viewport dimensions.

        Args:
            url: The site URL to capture.
            width: Viewport width in pixels.
            height: Viewport height in pixels.
            timeout: Navigation timeout in milliseconds (default 30 s).

        Returns:
            PNG image bytes.

        Raises:
            RuntimeError: If Playwright times out or encounters an error.
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout)
                png_bytes = page.screenshot(full_page=True)
                browser.close()
                return png_bytes
        except PlaywrightTimeout:
            raise RuntimeError(
                f"Playwright timed out after {timeout}ms navigating to {url}"
            )
        except Exception as exc:
            raise RuntimeError(f"Playwright screenshot failed: {exc}") from exc


class CompareService:
    """Compares two PNG images using pixelmatch and Pillow."""

    @staticmethod
    def compare(image_a_bytes: bytes, image_b_bytes: bytes, threshold: float = 0.1) -> dict:
        """Compare two PNG images using pixelmatch.

        Args:
            image_a_bytes: PNG bytes of the first image (e.g. Figma design).
            image_b_bytes: PNG bytes of the second image (e.g. live screenshot).
            threshold: Pixelmatch threshold (0.0 – 1.0, default 0.1).

        Returns:
            A dict with:
                mismatch_pixels: int
                mismatch_percentage: float
                diff_image_bytes: bytes (PNG)
                pass: bool  (True if mismatch_percentage <= 1.0)
        """
        image_a = Image.open(BytesIO(image_a_bytes)).convert("RGBA")
        image_b = Image.open(BytesIO(image_b_bytes)).convert("RGBA")

        # Resize image_b to match image_a if dimensions differ
        if image_a.size != image_b.size:
            image_b = image_b.resize(image_a.size, Image.LANCZOS)

        width, height = image_a.size
        diff_image = Image.new("RGBA", (width, height))

        mismatch_pixels = pixelmatch(image_a, image_b, diff_image, threshold=threshold)

        total_pixels = width * height
        mismatch_percentage = (mismatch_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0

        diff_buffer = BytesIO()
        diff_image.save(diff_buffer, format="PNG")
        diff_image_bytes = diff_buffer.getvalue()

        return {
            "mismatch_pixels": mismatch_pixels,
            "mismatch_percentage": round(mismatch_percentage, 2),
            "diff_image_bytes": diff_image_bytes,
            "pass": mismatch_percentage <= 1.0,
        }
