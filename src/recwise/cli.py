"""End-to-end CLI: import, match, reconcile, and export in one run.

Thin orchestration only -- no business logic lives here, per CLAUDE.md.
Every step below calls into the library module that owns that logic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from recwise.export import export_reconciliation
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.importer.errors import RecwiseImportError
from recwise.importer.loader import load_bank_statement, load_ledger
from recwise.importer.models import Transaction
from recwise.matching import MatchConfig, MatchRun, match
from recwise.matching.audit import AUDIT_LOG_FILENAME, append_entries, entries_from_match_run
from recwise.reconciliation import ReconciliationStatement, build_statement


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recwise-reconcile",
        description="Import a ledger and bank statement, match transactions, and "
        "produce a reconciliation statement with suggested journals.",
    )
    parser.add_argument("--ledger", type=Path, required=True, help="path to the ledger CSV/.xlsx")
    parser.add_argument(
        "--bank", type=Path, required=True, help="path to the bank statement CSV/.xlsx"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("output"), help="output directory (default: output)"
    )

    parser.add_argument("--ledger-date-col", default="date")
    parser.add_argument("--ledger-date-format", default="%Y-%m-%d")
    parser.add_argument("--ledger-description-col", default="description")
    parser.add_argument("--ledger-amount-col", default="amount")
    parser.add_argument("--ledger-account-col", default="account_ref")
    parser.add_argument("--ledger-id-col", default="id")

    parser.add_argument("--bank-date-col", default="date")
    parser.add_argument("--bank-date-format", default="%d/%m/%Y")
    parser.add_argument("--bank-description-col", default="description")
    parser.add_argument("--bank-debit-col", default="debit")
    parser.add_argument("--bank-credit-col", default="credit")
    parser.add_argument("--bank-account-col", default="account_ref")
    parser.add_argument("--bank-id-col", default="id")

    parser.add_argument(
        "--date-window-days",
        type=int,
        default=None,
        help="max days apart for a date-window match (default: engine default)",
    )
    return parser


def _print_summary(
    ledger: list[Transaction],
    bank: list[Transaction],
    run: MatchRun,
    statement: ReconciliationStatement,
    out_dir: Path,
) -> None:
    """Aggregate counts and balances only -- never individual descriptions,
    amounts, or account numbers, per CLAUDE.md's logging rule."""
    auto = run.auto_matches()
    review = run.review_matches()
    print(f"Loaded {len(ledger)} ledger row(s), {len(bank)} bank row(s).")
    print(f"Auto-matched: {len(auto)}  |  Needs review: {len(review)}")
    print(f"Unmatched ledger: {len(run.unmatched_ledger)}")
    print(f"Unmatched bank: {len(run.unmatched_bank)}")
    print(f"Balance per bank:   {statement.balance_per_bank}")
    print(f"Balance per ledger: {statement.balance_per_ledger}")
    print(f"Reconciled balance: {statement.reconciled_balance}")
    if statement.reconciled_balance != statement.balance_per_ledger:
        print("WARNING: reconciled balance does not match balance per ledger.", file=sys.stderr)
    print(f"Suggested journals: {len(statement.suggested_journals)}")
    print(f"Wrote reconciliation files to {out_dir}/")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ledger_mapping = LedgerColumnMapping(
        date_col=args.ledger_date_col,
        date_format=args.ledger_date_format,
        description_col=args.ledger_description_col,
        amount_col=args.ledger_amount_col,
        account_col=args.ledger_account_col,
        id_col=args.ledger_id_col,
    )
    bank_mapping = BankColumnMapping(
        date_col=args.bank_date_col,
        date_format=args.bank_date_format,
        description_col=args.bank_description_col,
        debit_col=args.bank_debit_col,
        credit_col=args.bank_credit_col,
        account_col=args.bank_account_col,
        id_col=args.bank_id_col,
    )

    try:
        ledger = load_ledger(args.ledger, ledger_mapping)
        bank = load_bank_statement(args.bank, bank_mapping)
    except RecwiseImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    match_config = MatchConfig()
    if args.date_window_days is not None:
        match_config = MatchConfig(date_window_days=args.date_window_days)

    run = match(ledger, bank, match_config)
    statement = build_statement(ledger, bank, run)

    export_reconciliation(args.out_dir, statement, run.matches)
    audit_entries = entries_from_match_run(run)
    append_entries(args.out_dir / AUDIT_LOG_FILENAME, audit_entries)

    _print_summary(ledger, bank, run, statement, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
