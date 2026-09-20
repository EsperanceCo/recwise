"""Normalize raw string cells into dates and clean descriptions.

Dates are parsed with an explicit, caller-supplied format -- never guessed
per row, since a guess that's wrong for one row in a batch is exactly the
kind of silent error this project exists to prevent.
"""

from __future__ import annotations

from datetime import date, datetime


def parse_txn_date(raw: str, date_format: str) -> date:
    stripped = raw.strip()
    try:
        return datetime.strptime(stripped, date_format).date()
    except ValueError as exc:
        raise ValueError(f"cannot parse {raw!r} as a date with format {date_format!r}") from exc


def clean_description(raw: str) -> str:
    """Collapse internal whitespace runs and strip leading/trailing whitespace.

    Deliberately does not alter casing or truncate -- those are data, not
    noise, once they reach the importer.
    """
    return " ".join(raw.split())
