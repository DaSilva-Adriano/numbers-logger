# numbers-logger

Personal macOS menu-bar app that watches a screen rectangle, OCRs it with Apple Vision, parses the first number, and appends rows to a CSV. Local only — no cloud APIs, no App Store.

## Install

1. Install [uv](https://docs.astral.sh/uv/):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. From this folder:

   ```bash
   uv sync
   ```

3. Grant **Screen Recording** to Terminal (or to the Python that `uv` runs: `.venv/bin/python`) in **System Settings → Privacy & Security → Screen Recording**. Quit and reopen after enabling.

4. Launch:

   ```bash
   uv run numbers-logger
   ```

## Use

The app lives in the menu bar (title `123`). On first launch, or if no region is saved, a dim overlay appears: drag a rectangle (Esc cancels).

| Menu | Action |
| --- | --- |
| Start watching | Capture → crop → Vision OCR → parse → CSV |
| Stop watching | Pause the watch loop |
| Select region… | Pick a new rectangle, then start watching |
| Open CSV | Create `~/numbers.csv` if needed and open it |
| Settings… | Interval, CSV path, log-only-on-change, min confidence |
| Quit | Stop watching and exit |

A CSV row is appended only when the parsed number **changes** (unless you turn that off). New values are also printed to stdout.

Settings and the last region are stored in `~/.numbers-logger/config.json`.

## Notes

- macOS only. OCR uses `ocrmac` (Apple Vision, `recognition_level="fast"`), not Tesseract.
- The region picker and settings window use AppKit (already pulled in by rumps). Tk 9.0 crashes on current macOS once AppKit owns `NSApplication`.
- Screenshots use `screencapture -x` of the full display, then Pillow crops the selection. Retina scale is `image_width / screen_width`. If that capture path fails, the app falls back to `mss`.
- Capture and OCR run on a background thread so the menu bar stays responsive.
- Default interval is 1.0s (minimum 0.2s). Default CSV header: `timestamp,value,raw,region`.
