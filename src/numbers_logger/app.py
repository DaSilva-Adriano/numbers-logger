"""Menu-bar app: watch a screen region and log parsed numbers."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from typing import Any

from numbers_logger.capture import (
    ScreenRecordingPermissionError,
    capture_region,
    has_screen_recording_permission,
    refresh_screens,
    request_screen_recording_permission,
)
from numbers_logger.ocr import image_to_text
from numbers_logger.parse import format_value, parse_number
from numbers_logger.store import (
    Region,
    append_row,
    auto_stop_elapsed,
    load_config,
    new_session_csv,
    save_config,
)

IDLE_TITLE = "123"
PERMISSION_MESSAGE = (
    "Enable this process in System Settings → Privacy & Security → Screen Recording, "
    "then quit and reopen."
)


def _require_rumps():
    try:
        import rumps
    except ImportError as exc:
        print("Missing dependency 'rumps'. Install with:\n  uv add rumps", file=sys.stderr)
        raise SystemExit(1) from exc
    return rumps


rumps = _require_rumps()


class NumbersLoggerApp(rumps.App):
    def __init__(self) -> None:
        super().__init__(IDLE_TITLE, quit_button=None)
        self.config = load_config()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watching = False
        self._bootstrapped = False
        self._permission_missing = False
        self._title_text = IDLE_TITLE
        self._last_value: float | None = None
        self._session_csv: str | None = None
        self._session_started_at: float | None = None

        self.start_item = rumps.MenuItem("Start watching", callback=self.start_watching)
        self.stop_item = rumps.MenuItem("Stop watching", callback=None)
        self.menu = [
            self.start_item,
            self.stop_item,
            None,
            rumps.MenuItem("Select region…", callback=self.select_region),
            rumps.MenuItem("Open CSV", callback=self.open_csv),
            rumps.MenuItem("Settings…", callback=self.open_settings),
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self._ui_timer = rumps.Timer(self._on_ui_timer, 0.25)
        self._ui_timer.start()

    def _on_ui_timer(self, _timer: rumps.Timer) -> None:
        hide_dock_icon()
        if self.title != self._title_text:
            self.title = self._title_text
        if self._permission_missing:
            self._permission_missing = False
            self._handle_permission_error()
            return
        if not self._bootstrapped:
            self._bootstrapped = True
            refresh_screens()
            if self.config.region is None:
                self.select_region(None)
            return
        self._maybe_auto_stop()

    def start_watching(self, _sender: rumps.MenuItem | None = None) -> None:
        with self._lock:
            config = self.config
        if config.region is None:
            self.select_region(None)
            return
        if not has_screen_recording_permission():
            request_screen_recording_permission()
            self._handle_permission_error()
            return
        if self._watching:
            return
        session = new_session_csv(config.expanded_csv_dir())
        self._stop.clear()
        self._last_value = None
        with self._lock:
            self._session_csv = str(session)
            self._session_started_at = time.monotonic()
        self._watching = True
        self._set_watching_menu(True)
        self._title_text = "…"
        print(f"logging to {session}", flush=True)
        self._thread = threading.Thread(target=self._watch_loop, name="watch", daemon=True)
        self._thread.start()

    def stop_watching(self, _sender: rumps.MenuItem | None = None) -> None:
        self._watching = False
        self._stop.set()
        thread = self._thread
        self._thread = None
        with self._lock:
            self._session_started_at = None
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=2.0)
        self._set_watching_menu(False)
        self._title_text = IDLE_TITLE

    def _maybe_auto_stop(self) -> None:
        if not self._watching:
            return
        with self._lock:
            config = self.config
            started = self._session_started_at
        if not auto_stop_elapsed(
            started,
            enabled=config.auto_stop_enabled,
            minutes=config.auto_stop_minutes,
            now=time.monotonic(),
        ):
            return
        print(f"auto-stopped after {config.auto_stop_minutes:g} minutes", flush=True)
        self.stop_watching(None)

    def select_region(self, _sender: rumps.MenuItem | None = None) -> None:
        was_watching = self._watching
        self.stop_watching(None)
        result = _run_helper("--pick-region")
        if result is None:
            with self._lock:
                has_region = self.config.region is not None
            if was_watching and has_region:
                self.start_watching(None)
            return
        try:
            region = Region(
                x=float(result["x"]),
                y=float(result["y"]),
                width=float(result["width"]),
                height=float(result["height"]),
                scale=float(result.get("scale", 1.0) or 1.0),
            )
        except (KeyError, TypeError, ValueError):
            rumps.alert("Could not read the selected region.")
            return
        if not region.is_valid():
            rumps.alert("The selected region is too small.")
            return
        with self._lock:
            self.config.region = region
            save_config(self.config)
        self.start_watching(None)

    def open_csv(self, _sender: rumps.MenuItem | None = None) -> None:
        with self._lock:
            session = self._session_csv
            folder = self.config.expanded_csv_dir()
        folder.mkdir(parents=True, exist_ok=True)
        target = session if session else str(folder)
        subprocess.run(["open", target], check=False)

    def open_settings(self, _sender: rumps.MenuItem | None = None) -> None:
        _run_helper("--settings", expect_json=False)
        with self._lock:
            self.config = load_config()

    def quit_app(self, _sender: rumps.MenuItem | None = None) -> None:
        self.stop_watching(None)
        rumps.quit_application()

    def _watch_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._tick()
            except ScreenRecordingPermissionError:
                self._permission_missing = True
                self._watching = False
                break
            except Exception as exc:
                print(f"watch error: {exc}", file=sys.stderr)
            with self._lock:
                interval = max(0.2, float(self.config.interval_seconds))
            remaining = interval - (time.monotonic() - started)
            self._stop.wait(timeout=max(0.0, remaining))

    def _tick(self) -> None:
        with self._lock:
            config = self.config
            last_value = self._last_value
        if config.region is None:
            return
        image = capture_region(config.region)
        if image is None:
            return
        raw = image_to_text(image, min_confidence=config.min_confidence)
        if not raw.strip():
            return
        value = parse_number(raw)
        if value is None:
            return
        if config.log_only_on_change and last_value is not None and value == last_value:
            return
        with self._lock:
            session = self._session_csv
        if not session:
            return
        append_row(value=value, raw=raw, region=config.region, csv_path=session)
        print(format_value(value), flush=True)
        with self._lock:
            self._last_value = value
        self._title_text = _title_for_value(value)

    def _set_watching_menu(self, watching: bool) -> None:
        self.start_item.set_callback(None if watching else self.start_watching)
        self.stop_item.set_callback(self.stop_watching if watching else None)

    def _handle_permission_error(self) -> None:
        self.stop_watching(None)
        rumps.alert(
            title="Screen Recording permission required",
            message=PERMISSION_MESSAGE,
            ok="Quit",
        )
        rumps.quit_application()


def _title_for_value(value: float) -> str:
    text = format_value(value)
    if len(text) > 10:
        return format(value, ".4g")
    return text


def _run_helper(flag: str, expect_json: bool = True) -> dict[str, Any] | None:
    cmd = [sys.executable, "-m", "numbers_logger", flag]
    if expect_json:
        proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, text=True)
    else:
        proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        return None
    if not expect_json:
        return {}
    stdout = (proc.stdout or "").strip()
    if not stdout or stdout == "null":
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def hide_dock_icon() -> None:
    try:
        from AppKit import NSApp, NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication()
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def run() -> None:
    if sys.platform != "darwin":
        print("numbers-logger only runs on macOS.", file=sys.stderr)
        raise SystemExit(1)
    refresh_screens()
    app = NumbersLoggerApp()
    hide_dock_icon()
    app.run()
