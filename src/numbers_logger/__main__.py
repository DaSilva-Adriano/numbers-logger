"""CLI entry point for `uv run numbers-logger`."""

from __future__ import annotations

import argparse
import sys


def _check_import(import_name: str, package: str) -> None:
    try:
        __import__(import_name)
    except ImportError:
        print(f"Missing dependency '{package}'. Install with:\n  uv add {package}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="numbers-logger",
        description="Menu-bar app that OCRs a selected screen region and logs numbers to CSV.",
    )
    parser.add_argument("--pick-region", action="store_true", help="Run the region picker and print JSON")
    parser.add_argument("--settings", action="store_true", help="Open the settings window")
    args = parser.parse_args()

    if args.pick_region:
        from numbers_logger.overlay import run_picker_cli

        raise SystemExit(run_picker_cli())
    if args.settings:
        from numbers_logger.overlay import run_settings_cli

        raise SystemExit(run_settings_cli())

    _check_import("ocrmac", "ocrmac")
    _check_import("PIL", "pillow")
    _check_import("rumps", "rumps")

    from numbers_logger.app import run

    run()


if __name__ == "__main__":
    main()
