import json
import tempfile
import unittest
from pathlib import Path

from numbers_logger.store import (
    DEFAULT_AUTO_START_MINUTES,
    DEFAULT_AUTO_STOP_MINUTES,
    MIN_AUTO_START_MINUTES,
    MIN_AUTO_STOP_MINUTES,
    Config,
    duration_elapsed,
    load_config,
    save_config,
)


class AutoStopConfigTests(unittest.TestCase):
    def test_missing_keys_use_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"interval_seconds": 2.0, "csv_path": "/tmp/out"}) + "\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertFalse(config.auto_stop_enabled)
            self.assertEqual(config.auto_stop_minutes, DEFAULT_AUTO_STOP_MINUTES)
            self.assertFalse(config.auto_start_enabled)
            self.assertEqual(config.auto_start_minutes, DEFAULT_AUTO_START_MINUTES)

    def test_save_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            original = Config(
                auto_stop_enabled=True,
                auto_stop_minutes=15.0,
                auto_start_enabled=True,
                auto_start_minutes=5.0,
            )
            save_config(original, path)
            loaded = load_config(path)
            self.assertTrue(loaded.auto_stop_enabled)
            self.assertEqual(loaded.auto_stop_minutes, 15.0)
            self.assertTrue(loaded.auto_start_enabled)
            self.assertEqual(loaded.auto_start_minutes, 5.0)

    def test_minutes_below_minimum_are_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"auto_stop_enabled": True, "auto_stop_minutes": 0}) + "\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.auto_stop_minutes, MIN_AUTO_STOP_MINUTES)

    def test_invalid_minutes_use_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"auto_stop_minutes": "nope", "auto_start_minutes": "nope"})
                + "\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.auto_stop_minutes, DEFAULT_AUTO_STOP_MINUTES)
            self.assertEqual(config.auto_start_minutes, DEFAULT_AUTO_START_MINUTES)

    def test_auto_start_minutes_below_minimum_are_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"auto_start_enabled": True, "auto_start_minutes": 0}) + "\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.auto_start_minutes, MIN_AUTO_START_MINUTES)


class DurationElapsedTests(unittest.TestCase):
    def test_disabled_never_elapses(self) -> None:
        self.assertFalse(duration_elapsed(0.0, enabled=False, minutes=1, now=120.0))

    def test_missing_start_never_elapses(self) -> None:
        self.assertFalse(duration_elapsed(None, enabled=True, minutes=1, now=120.0))

    def test_before_duration(self) -> None:
        self.assertFalse(duration_elapsed(0.0, enabled=True, minutes=1, now=59.9))

    def test_at_duration(self) -> None:
        self.assertTrue(duration_elapsed(0.0, enabled=True, minutes=1, now=60.0))

    def test_after_duration(self) -> None:
        self.assertTrue(duration_elapsed(10.0, enabled=True, minutes=2, now=130.0))

    def test_new_session_uses_new_start(self) -> None:
        self.assertFalse(duration_elapsed(200.0, enabled=True, minutes=1, now=230.0))
        self.assertTrue(duration_elapsed(200.0, enabled=True, minutes=1, now=260.0))


if __name__ == "__main__":
    unittest.main()
