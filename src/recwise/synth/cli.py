"""CLI entry point for the synthetic data generator."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from recwise.synth.generator import SynthConfig, generate
from recwise.synth.writer import write_all


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recwise-synth",
        description="Generate a synthetic ledger + bank statement pair with a known answer key.",
    )
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="approximate number of ledger transactions (default: 1000)",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=date(2024, 1, 1),
        help="first possible transaction date, YYYY-MM-DD (default: 2024-01-01)",
    )
    parser.add_argument(
        "--num-days",
        type=int,
        default=90,
        help="span of days transactions are spread across (default: 90)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sample_data"),
        help="output directory (default: sample_data)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.count <= 0:
        parser.error("--count must be positive")
    if args.num_days <= 0:
        parser.error("--num-days must be positive")

    config = SynthConfig(
        seed=args.seed, count=args.count, start_date=args.start_date, num_days=args.num_days
    )
    data = generate(config)
    write_all(args.out_dir, data)
    print(
        f"Wrote {len(data.ledger_rows)} ledger rows, {len(data.bank_rows)} bank rows, "
        f"{len(data.cases)} planted cases to {args.out_dir}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
