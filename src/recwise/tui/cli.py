"""CLI entry point for the terminal review UI."""

from __future__ import annotations

import argparse

from recwise.cli import build_parser as build_reconcile_parser
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.matching import MatchConfig
from recwise.tui.app import RecwiseApp
from recwise.tui.session import SessionConfig


def build_parser() -> argparse.ArgumentParser:
    # Reuse recwise-reconcile's ledger/bank/out-dir/column-mapping flags.
    parser = build_reconcile_parser()
    parser.prog = "recwise-tui"
    parser.description = "Start the terminal review UI for a ledger/bank statement pair."
    return parser


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
    match_config = MatchConfig()
    if args.date_window_days is not None:
        match_config = MatchConfig(date_window_days=args.date_window_days)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    session = SessionConfig(
        ledger_path=args.ledger,
        bank_path=args.bank,
        ledger_mapping=ledger_mapping,
        bank_mapping=bank_mapping,
        out_dir=args.out_dir,
        match_config=match_config,
    )
    RecwiseApp(session).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
