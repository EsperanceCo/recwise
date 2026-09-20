"""CLI entry point for the review web app.

Binds to 127.0.0.1 only -- not a configurable flag, per CLAUDE.md's
"if the UI runs a local server, bind to 127.0.0.1 only" rule.
"""

from __future__ import annotations

import argparse
import webbrowser

from recwise.cli import build_parser as build_reconcile_parser
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.matching import MatchConfig
from recwise.web.app import create_app

HOST = "127.0.0.1"


def build_parser() -> argparse.ArgumentParser:
    # Reuse recwise-reconcile's ledger/bank/out-dir/column-mapping flags
    # rather than redefining them.
    parser = build_reconcile_parser()
    parser.prog = "recwise-review"
    parser.description = "Start the local review web app for a ledger/bank statement pair."
    parser.add_argument("--port", type=int, default=5000, help="port to listen on (default: 5000)")
    parser.add_argument(
        "--no-browser", action="store_true", help="don't open a browser window automatically"
    )
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

    app = create_app(
        ledger_path=args.ledger,
        bank_path=args.bank,
        ledger_mapping=ledger_mapping,
        bank_mapping=bank_mapping,
        out_dir=args.out_dir,
        match_config=match_config,
    )

    url = f"http://{HOST}:{args.port}/"
    print(f"Recwise review running at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    app.run(host=HOST, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
