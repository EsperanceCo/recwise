"""CLI for audit analytics: recwise-audit.

Standalone -- takes any single ledger- or bank-shaped file (reusing
recwise.importer, same as recwise-reconcile) and reports a Benford's
Law first-digit analysis. Does not require a matched ledger/bank pair.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from recwise.analytics.benford import BenfordResult, analyze
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.importer.errors import RecwiseImportError
from recwise.importer.loader import load_bank_statement, load_ledger
from recwise.importer.models import Transaction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recwise-audit",
        description="Run audit analytics (Benford's Law first-digit test) on a transaction file.",
    )
    parser.add_argument("--file", type=Path, required=True, help="path to the CSV/.xlsx file")
    parser.add_argument(
        "--kind",
        choices=["ledger", "bank"],
        default="ledger",
        help="column layout: 'ledger' (single amount column) or "
        "'bank' (separate debit/credit columns). Default: ledger",
    )

    parser.add_argument("--date-col", default="date")
    parser.add_argument("--date-format", default="%Y-%m-%d")
    parser.add_argument("--description-col", default="description")
    parser.add_argument("--account-col", default="account_ref")
    parser.add_argument("--id-col", default="id")
    parser.add_argument("--amount-col", default="amount", help="ledger only")
    parser.add_argument("--debit-col", default="debit", help="bank only")
    parser.add_argument("--credit-col", default="credit", help="bank only")
    return parser


def _load(args: argparse.Namespace) -> list[Transaction]:
    if args.kind == "ledger":
        mapping = LedgerColumnMapping(
            date_col=args.date_col,
            date_format=args.date_format,
            description_col=args.description_col,
            amount_col=args.amount_col,
            account_col=args.account_col,
            id_col=args.id_col,
        )
        return load_ledger(args.file, mapping)

    bank_mapping = BankColumnMapping(
        date_col=args.date_col,
        date_format=args.date_format,
        description_col=args.description_col,
        debit_col=args.debit_col,
        credit_col=args.credit_col,
        account_col=args.account_col,
        id_col=args.id_col,
    )
    return load_bank_statement(args.file, bank_mapping)


def _print_report(result: BenfordResult) -> None:
    print(f"Sample size: {result.sample_size}")
    if not result.sufficient_sample:
        print(
            f"WARNING: sample size {result.sample_size} is under the "
            "recommended minimum of 300 for a meaningful first-digit test; "
            "treat this result as indicative only.",
            file=sys.stderr,
        )
    print()
    print(f"{'Digit':>5}  {'Observed':>9}  {'Obs %':>7}  {'Expected %':>10}  {'Deviation':>9}")
    for stat in result.digit_stats:
        print(
            f"{stat.digit:>5}  {stat.observed_count:>9}  "
            f"{stat.observed_proportion * 100:>6.2f}%  "
            f"{stat.expected_proportion * 100:>9.2f}%  "
            f"{stat.absolute_deviation * 100:>8.2f}%"
        )
    print()
    print(f"Mean absolute deviation: {result.mean_absolute_deviation:.4f}")
    print(f"Conformity: {result.conformity.value}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        transactions = _load(args)
    except (RecwiseImportError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = analyze(transactions)
    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
