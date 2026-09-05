"""Screenshot a selected region. Full-screen capture, then Pillow crop."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from numbers_logger.store import Region

SCREENSHOT_PATH = Path("/tmp/numbers-logger-full.png")


class ScreenRecordingPermissionError(PermissionError):
    """macOS Screen Recording permission is missing for this process."""


@dataclass(frozen=True)
class Screen:
    x: int
    y: int
    width: int
    height: int
    scale: float
    index: int

    @property
    def max_x(self) -> int:
        return self.x + self.width

    @property
    def max_y(self) -> int:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.max_x and self.y <= y < self.max_y


_screens_cache: list[Screen] = []


def _require_pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        print("Missing dependency 'pillow'. Install with:\n  uv add pillow", file=sys.stderr)
        raise SystemExit(1) from exc
    return Image


def refresh_screens() -> list[Screen]:
    """Cache display geometry. Call from the main thread."""
    global _screens_cache
    screens = _list_screens_appkit()
    if screens:
        _screens_cache = screens
    return list(_screens_cache)


def list_screens() -> list[Screen]:
    if _screens_cache:
        return list(_screens_cache)
    screens = _list_screens_appkit()
    if screens:
        return screens
    return [Screen(x=0, y=0, width=1920, height=1080, scale=1.0, index=1)]


def screen_containing(x: float, y: float, screens: list[Screen] | None = None) -> Screen | None:
    items = screens if screens is not None else list_screens()
    for screen in items:
        if screen.contains(x, y):
            return screen
    return items[0] if items else None


def has_screen_recording_permission() -> bool:
    try:
        from Quartz import CGPreflightScreenCaptureAccess
    except ImportError:
        return True
    try:
        return bool(CGPreflightScreenCaptureAccess())
    except Exception:
        return True


def request_screen_recording_permission() -> bool:
    try:
        from Quartz import CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess
    except ImportError:
        return True
    try:
        if CGPreflightScreenCaptureAccess():
            return True
        CGRequestScreenCaptureAccess()
        return bool(CGPreflightScreenCaptureAccess())
    except Exception:
        return True


def capture_region(region: Region) -> Any:
    """Return a cropped PIL image of `region`, or None if the crop is empty."""
    Image = _require_pillow()
    try:
        image = _capture_screencapture(region)
    except ScreenRecordingPermissionError:
        raise
    except Exception as exc:
        print(f"screencapture failed ({exc}); falling back to mss", file=sys.stderr)
        image = None
    if image is not None:
        return image
    try:
        return _capture_mss(region, Image)
    except ScreenRecordingPermissionError:
        raise
    except ImportError as exc:
        print("Missing dependency 'mss'. Install with:\n  uv add mss", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"mss fallback failed ({exc})", file=sys.stderr)
        return None


def _capture_screencapture(region: Region):
    # Primary path required by the spec: full-screen capture, then crop.
    image = _run_screencapture(None)
    if _looks_blank(image):
        raise ScreenRecordingPermissionError("screenshot was blank")

    main = _main_screen()
    target = screen_containing(
        region.x + region.width / 2.0,
        region.y + region.height / 2.0,
    )
    on_main = target is None or main is None or target.index == main.index
    if on_main:
        origin_x = main.x if main is not None else 0
        origin_y = main.y if main is not None else 0
        points_width = main.width if main is not None else (image.width / max(region.scale, 0.1))
        scale = _detect_scale(image.width, points_width, region.scale)
        cropped = _crop(
            image,
            region.x - origin_x,
            region.y - origin_y,
            region.width,
            region.height,
            scale,
        )
        if cropped is not None:
            return cropped

    if target is not None and not on_main:
        try:
            other = _run_screencapture(target.index)
        except Exception:
            other = None
        if other is not None and not _looks_blank(other):
            scale = _detect_scale(other.width, target.width, region.scale)
            cropped = _crop(
                other,
                region.x - target.x,
                region.y - target.y,
                region.width,
                region.height,
                scale,
            )
            if cropped is not None:
                return cropped

    raise RuntimeError("crop is outside the captured display")


def _run_screencapture(display_index: int | None):
    Image = _require_pillow()
    cmd = ["screencapture", "-x"]
    if display_index is not None:
        cmd.append(f"-D{display_index}")
    cmd.append(str(SCREENSHOT_PATH))
    result = subprocess.run(cmd, check=False, capture_output=True, timeout=8)
    if result.returncode != 0 or not SCREENSHOT_PATH.exists():
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"screencapture exited {result.returncode}")
    with Image.open(SCREENSHOT_PATH) as raw:
        return raw.convert("RGB")


def _capture_mss(region: Region, Image):
    try:
        import mss
    except ImportError:
        raise

    screen = screen_containing(
        region.x + region.width / 2.0,
        region.y + region.height / 2.0,
    )
    with mss.mss() as sct:
        monitors = sct.monitors
        grab: dict[str, int]
        if screen is not None and screen.index < len(monitors):
            monitor = monitors[screen.index]
            scale = monitor["width"] / screen.width if screen.width else region.scale
            if scale <= 0:
                scale = region.scale if region.scale > 0 else 1.0
            grab = {
                "left": monitor["left"] + int(round((region.x - screen.x) * scale)),
                "top": monitor["top"] + int(round((region.y - screen.y) * scale)),
                "width": max(1, int(round(region.width * scale))),
                "height": max(1, int(round(region.height * scale))),
            }
        else:
            scale = region.scale if region.scale > 0 else 1.0
            grab = {
                "left": int(round(region.x * scale)),
                "top": int(round(region.y * scale)),
                "width": max(1, int(round(region.width * scale))),
                "height": max(1, int(round(region.height * scale))),
            }
        shot = sct.grab(grab)
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if _looks_blank(image) and image.width > 8 and image.height > 8:
        raise ScreenRecordingPermissionError("screenshot was blank")
    return image


def _crop(image, x: float, y: float, width: float, height: float, scale: float):
    left = int(round(x * scale))
    top = int(round(y * scale))
    right = int(round((x + width) * scale))
    bottom = int(round((y + height) * scale))
    left = max(0, min(left, image.width))
    top = max(0, min(top, image.height))
    right = max(0, min(right, image.width))
    bottom = max(0, min(bottom, image.height))
    if right - left < 2 or bottom - top < 2:
        return None
    return image.crop((left, top, right, bottom))


def _detect_scale(image_width: int, screen_width: float, fallback: float) -> float:
    if screen_width <= 0:
        return fallback if fallback > 0 else 1.0
    scale = image_width / screen_width
    if 0.9 <= scale <= 4.1:
        return scale
    return fallback if fallback > 0 else 1.0


def _looks_blank(image) -> bool:
    sample = image.convert("L").resize((32, 32))
    extrema = sample.getextrema()
    return extrema is not None and extrema[1] <= 2


def _main_screen() -> Screen | None:
    screens = list_screens()
    for screen in screens:
        if screen.index == 1:
            return screen
    return screens[0] if screens else None


def _list_screens_appkit() -> list[Screen]:
    try:
        from AppKit import NSScreen
    except ImportError:
        return []
    screens = NSScreen.screens()
    if not screens:
        return []
    main_height = float(screens[0].frame().size.height)
    result: list[Screen] = []
    for index, screen in enumerate(screens, start=1):
        frame = screen.frame()
        width = int(round(frame.size.width))
        height = int(round(frame.size.height))
        x = int(round(frame.origin.x))
        y = int(round(main_height - (frame.origin.y + frame.size.height)))
        scale = float(screen.backingScaleFactor())
        result.append(
            Screen(x=x, y=y, width=width, height=height, scale=scale or 1.0, index=index)
        )
    return result
