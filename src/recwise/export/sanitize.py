"""Spreadsheet formula-injection protection.

Any text cell starting with `=`, `+`, `-`, `@`, a tab, or a carriage return
can be interpreted as a formula (or worse) when the exported file is
reopened in Excel/Sheets/LibreOffice. Every text value written by the
export module goes through sanitize_cell() first. Negative numbers are
never sanitized -- they're written as actual numeric values, not text, so
this function is only ever called on text cells.
"""

from __future__ import annotations

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: str) -> str:
    """Prefix a text cell with `'` if it starts with a formula-triggering
    character. Only for text cells -- never call this on a numeric value
    (e.g. a formatted Decimal amount); those stay numeric on purpose.
    """
    if value.startswith(_DANGEROUS_PREFIXES):
        return f"'{value}"
    return value
