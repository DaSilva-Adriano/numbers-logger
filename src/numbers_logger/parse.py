"""Extract the first plausible number from OCR text."""

from __future__ import annotations

import math
import re

_NUMBER_RE = re.compile(
    r"""
    [+-]?
    (?:
        \d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?   # grouped thousands
        |\d+(?:[.,]\d+)?                     # integer or simple decimal
    )
    (?:[eE][+-]?\d+)?
    %?
    """,
    re.VERBOSE,
)

_UNICODE_MINUS = str.maketrans(
    {
        "\u2212": "-",  # minus
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\uff0b": "+",  # fullwidth plus
        "\uff0d": "-",  # fullwidth hyphen
    }
)


def parse_number(text: str) -> float | None:
    """Return the first plausible number in `text`, or None if none is found.

    Accepts 1234, 1,234.56, 1.234,56, 12.3%, 1.2e3, and a leading +/−.
    Spaces and thin spaces are stripped. If both comma and dot appear, the
    last separator is the decimal mark.
    """
    if not text:
        return None
    compact = _prepare(text)
    match = _NUMBER_RE.search(compact)
    if match is None:
        return None
    return _token_to_float(match.group(0))


def format_value(value: float) -> str:
    """Format a parsed number for CSV and the menu bar."""
    if math.isfinite(value) and value == math.trunc(value) and abs(value) < 1e15:
        return str(int(value))
    return format(value, ".12g")


def _prepare(text: str) -> str:
    translated = text.translate(_UNICODE_MINUS)
    return "".join(ch for ch in translated if not ch.isspace())


def _token_to_float(token: str) -> float | None:
    token = token.rstrip("%")
    if not token or token in {"+", "-"}:
        return None

    sign = ""
    if token[0] in "+-":
        sign = "-" if token[0] == "-" else ""
        token = token[1:]

    exponent = ""
    exp_match = re.search(r"[eE][+-]?\d+$", token)
    if exp_match is not None:
        exponent = token[exp_match.start() :]
        token = token[: exp_match.start()]

    try:
        normalized = _normalize_decimal(token)
        return float(f"{sign}{normalized}{exponent}")
    except ValueError:
        return None


def _normalize_decimal(number: str) -> str:
    has_dot = "." in number
    has_comma = "," in number
    if has_dot and has_comma:
        if number.rfind(",") > number.rfind("."):
            return number.replace(".", "").replace(",", ".")
        return number.replace(",", "")
    if has_comma:
        if number.count(",") > 1:
            return _collapse_separators(number, ",")
        return number.replace(",", ".")
    if number.count(".") > 1:
        return _collapse_separators(number, ".")
    return number


def _collapse_separators(number: str, separator: str) -> str:
    parts = number.split(separator)
    if len(parts) < 2:
        return number
    if all(len(part) == 3 for part in parts[1:]):
        return "".join(parts)
    return "".join(parts[:-1]) + "." + parts[-1]
