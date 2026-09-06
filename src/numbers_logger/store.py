"""Persistent settings (`~/.numbers-logger/config.json`) and CSV logging."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from numbers_logger.parse import format_value

CONFIG_DIR = Path.home() / ".numbers-logger"
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_CSV_DIR = str(Path.home() / "Documents" / "numbers-logger")
CSV_HEADER = ["timestamp", "value", "raw", "region"]
MIN_INTERVAL_SECONDS = 0.2
MIN_TIMER_MINUTES = 1.0
MIN_AUTO_STOP_MINUTES = MIN_TIMER_MINUTES
MIN_AUTO_START_MINUTES = MIN_TIMER_MINUTES
DEFAULT_AUTO_STOP_MINUTES = 60.0
DEFAULT_AUTO_START_MINUTES = 60.0


@dataclass
class Region:
    x: float
    y: float
    width: float
    height: float
    scale: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
        }

    def csv_cell(self) -> str:
        return f"x={self.x:g},y={self.y:g},w={self.width:g},h={self.height:g}"

    def is_valid(self) -> bool:
        return self.width >= 2 and self.height >= 2


@dataclass
class Config:
    interval_seconds: float = 1.0
    csv_path: str = DEFAULT_CSV_DIR
    log_only_on_change: bool = True
    min_confidence: float = 0.3
    auto_stop_enabled: bool = False
    auto_stop_minutes: float = DEFAULT_AUTO_STOP_MINUTES
    auto_start_enabled: bool = False
    auto_start_minutes: float = DEFAULT_AUTO_START_MINUTES
    region: Region | None = field(default=None)

    def expanded_csv_dir(self) -> Path:
        return Path(self.csv_path).expanduser()


def load_config(path: Path | None = None) -> Config:
    config_path = path or CONFIG_PATH
    if not config_path.exists():
        return Config()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read {config_path}: {exc}. Using defaults.")
        return Config()
    if not isinstance(data, dict):
        return Config()
    return Config(
        interval_seconds=_clamp_interval(data.get("interval_seconds", 1.0)),
        csv_path=_normalize_csv_dir(
            _as_str(data.get("csv_dir") or data.get("csv_path"), DEFAULT_CSV_DIR)
        ),
        log_only_on_change=_as_bool(data.get("log_only_on_change"), True),
        min_confidence=_clamp_confidence(data.get("min_confidence", 0.3)),
        auto_stop_enabled=_as_bool(data.get("auto_stop_enabled"), False),
        auto_stop_minutes=_clamp_minutes(
            data.get("auto_stop_minutes"), default=DEFAULT_AUTO_STOP_MINUTES
        ),
        auto_start_enabled=_as_bool(data.get("auto_start_enabled"), False),
        auto_start_minutes=_clamp_minutes(
            data.get("auto_start_minutes"), default=DEFAULT_AUTO_START_MINUTES
        ),
        region=_parse_region(data.get("region")),
    )


def save_config(config: Config, path: Path | None = None) -> None:
    config_path = path or CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "interval_seconds": _clamp_interval(config.interval_seconds),
        "csv_path": config.csv_path,
        "log_only_on_change": bool(config.log_only_on_change),
        "min_confidence": _clamp_confidence(config.min_confidence),
        "auto_stop_enabled": bool(config.auto_stop_enabled),
        "auto_stop_minutes": _clamp_minutes(
            config.auto_stop_minutes, default=DEFAULT_AUTO_STOP_MINUTES
        ),
        "auto_start_enabled": bool(config.auto_start_enabled),
        "auto_start_minutes": _clamp_minutes(
            config.auto_start_minutes, default=DEFAULT_AUTO_START_MINUTES
        ),
        "region": config.region.as_dict() if config.region is not None else None,
    }
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config_path)


def new_session_csv(directory: str | Path, when: datetime | None = None) -> Path:
    """Create a timestamped CSV in `directory` and write the header."""
    folder = Path(directory).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    path = folder / f"numbers-{stamp}.csv"
    suffix = 2
    while path.exists():
        path = folder / f"numbers-{stamp}_{suffix}.csv"
        suffix += 1
    ensure_csv(path)
    return path


def ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(CSV_HEADER)
        handle.flush()


def append_row(
    *,
    value: float,
    raw: str,
    region: Region,
    csv_path: str,
    timestamp: datetime | None = None,
) -> None:
    path = Path(csv_path).expanduser()
    ensure_csv(path)
    stamp = (timestamp or datetime.now().astimezone()).isoformat(timespec="seconds")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([stamp, format_value(value), raw, region.csv_cell()])
        handle.flush()


def _parse_region(value: Any) -> Region | None:
    if not isinstance(value, dict):
        return None
    try:
        region = Region(
            x=float(value["x"]),
            y=float(value["y"]),
            width=float(value["width"]),
            height=float(value["height"]),
            scale=float(value.get("scale", 1.0) or 1.0),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not region.is_valid():
        return None
    if region.scale <= 0:
        region.scale = 1.0
    return region


def _clamp_interval(value: Any) -> float:
    try:
        interval = float(value)
    except (TypeError, ValueError):
        interval = 1.0
    return max(MIN_INTERVAL_SECONDS, interval)


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.3
    return min(1.0, max(0.0, confidence))


def _clamp_minutes(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_TIMER_MINUTES, minutes)


def duration_elapsed(
    started_at: float | None,
    *,
    enabled: bool,
    minutes: float,
    now: float,
) -> bool:
    """True when an auto-start or auto-stop timer has reached its duration."""
    if not enabled or started_at is None:
        return False
    try:
        duration = float(minutes) * 60.0
    except (TypeError, ValueError):
        return False
    if duration <= 0:
        return False
    return now - started_at >= duration


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_str(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def _normalize_csv_dir(value: str) -> str:
    """Treat settings as a folder. Old configs stored a file path."""
    path = Path(value).expanduser()
    old_default = Path.home() / "numbers.csv"
    if path == old_default:
        return DEFAULT_CSV_DIR
    if value.lower().endswith(".csv") or (path.exists() and path.is_file()):
        parent = path.parent
        return str(parent) if str(parent) not in {"", "."} else DEFAULT_CSV_DIR
    return str(path)
