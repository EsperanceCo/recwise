#!/usr/bin/env python3
"""Pre-commit hook: reject staged csv/xlsx/xls/pdf files outside sample_data/."""

from __future__ import annotations

import sys
from pathlib import Path

BLOCKED_SUFFIXES = {".csv", ".xlsx", ".xls", ".pdf"}
ALLOWED_PREFIX = "sample_data/"


def main(argv: list[str]) -> int:
    violations = [
        path
        for path in argv
        if Path(path).suffix.lower() in BLOCKED_SUFFIXES
        and not path.replace("\\", "/").startswith(ALLOWED_PREFIX)
    ]
    if violations:
        print("Blocked: spreadsheet/data files outside sample_data/:", file=sys.stderr)
        for path in violations:
            print(f"  {path}", file=sys.stderr)
        print(
            "Only synthetic data under sample_data/ may be committed. See CLAUDE.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
