"""OCR a cropped screenshot with Apple Vision via ocrmac."""

from __future__ import annotations

import sys
from typing import Any


def _require_ocrmac():
    try:
        from ocrmac import ocrmac
    except ImportError as exc:
        print("Missing dependency 'ocrmac'. Install with:\n  uv add ocrmac", file=sys.stderr)
        raise SystemExit(1) from exc
    return ocrmac


def image_to_text(image: Any, min_confidence: float = 0.3) -> str:
    """Return recognized text from a PIL image, or "" if nothing is found."""
    if image is None:
        return ""
    ocrmac = _require_ocrmac()
    confidence = min(1.0, max(0.0, float(min_confidence)))
    try:
        converted = image.convert("RGB") if getattr(image, "mode", "RGB") != "RGB" else image
        annotations = ocrmac.OCR(
            converted,
            recognition_level="fast",
            confidence_threshold=confidence,
        ).recognize()
    except Exception as exc:
        print(f"OCR failed: {exc}", file=sys.stderr)
        return ""

    parts: list[str] = []
    for item in annotations or []:
        if not item:
            continue
        text = str(item[0]).strip()
        score = float(item[1]) if len(item) > 1 else 1.0
        if text and score >= confidence:
            parts.append(text)
    return " ".join(parts)
