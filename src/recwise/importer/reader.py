"""Read CSV/Excel files into string-typed DataFrames. Read-only, size-capped.

Amount columns are never inferred here -- everything comes back as `str`,
including on Excel sheets where openpyxl would otherwise hand back floats
for numeric cells. Conversion to Decimal happens later, in normalize.py,
via recwise.money.parse_amount.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from recwise.importer.errors import FileTooLargeError, UnsupportedFileTypeError

# Untrusted input files are capped well above any realistic accounting
# export; this exists to fail fast on a mistaken or hostile huge file
# rather than to accommodate any known legitimate use case.
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

_CSV_SUFFIXES = {".csv"}
_EXCEL_SUFFIXES = {".xlsx"}


def _check_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {path}")
    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"{path.name} is {size:,} bytes, exceeding the {MAX_FILE_SIZE_BYTES:,} byte cap"
        )


def _all_string_dtypes(df: pd.DataFrame) -> dict[str, str]:
    return dict.fromkeys(df.columns, "string")


def read_table(path: Path) -> pd.DataFrame:
    """Read a CSV or .xlsx file into a DataFrame where every cell is a string.

    Never infers types: numbers, dates, and blanks all come back as their
    literal text (or the empty string), so callers control every conversion.
    """
    path = Path(path)
    _check_file(path)
    suffix = path.suffix.lower()

    if suffix in _CSV_SUFFIXES:
        # Read once to get column names, then re-read with every column
        # forced to string dtype -- avoids pandas guessing int/float/bool
        # for any column, amounts included.
        header_only = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
        return pd.read_csv(
            path,
            dtype=_all_string_dtypes(header_only),
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    if suffix in _EXCEL_SUFFIXES:
        header_only = pd.read_excel(path, nrows=0, engine="openpyxl")
        return pd.read_excel(
            path,
            dtype=_all_string_dtypes(header_only),
            keep_default_na=False,
            engine="openpyxl",
        )
    raise UnsupportedFileTypeError(
        f"unsupported file type {suffix!r} for {path.name}; expected .csv or .xlsx"
    )
