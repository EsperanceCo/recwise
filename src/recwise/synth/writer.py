"""Write generated ledger/bank/answer-key files to disk.

The ledger and bank statement are deliberately in different formats (date
style, decimal separator, column layout) per the project's synthetic-data
requirements.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from recwise.money import bank_amount_to_signed, format_decimal_comma, format_decimal_dot
from recwise.synth.generator import GeneratedData

LEDGER_DATE_FMT = "%Y-%m-%d"
BANK_DATE_FMT = "%d/%m/%Y"

LEDGER_FILENAME = "ledger.csv"
BANK_FILENAME = "bank_statement.csv"
ANSWER_KEY_FILENAME = "answer_key.json"


def write_ledger_csv(path: Path, data: GeneratedData) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "date", "description", "amount", "account_ref"])
        for row in data.ledger_rows:
            writer.writerow(
                [
                    row.id,
                    row.txn_date.strftime(LEDGER_DATE_FMT),
                    row.description,
                    format_decimal_dot(row.amount),
                    row.account_ref,
                ]
            )


def write_bank_csv(path: Path, data: GeneratedData) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "date", "description", "debit", "credit", "account_ref"])
        for row in data.bank_rows:
            writer.writerow(
                [
                    row.id,
                    row.txn_date.strftime(BANK_DATE_FMT),
                    row.description,
                    format_decimal_comma(row.debit) if row.debit is not None else "",
                    format_decimal_comma(row.credit) if row.credit is not None else "",
                    row.account_ref,
                ]
            )


def compute_balances(data: GeneratedData) -> tuple[Decimal, Decimal]:
    """Return (balance_per_ledger, balance_per_bank) from the in-memory rows."""
    balance_per_ledger = sum((row.amount for row in data.ledger_rows), Decimal("0"))
    balance_per_bank = sum(
        (bank_amount_to_signed(row.debit, row.credit) for row in data.bank_rows), Decimal("0")
    )
    return balance_per_ledger, balance_per_bank


def write_answer_key(path: Path, data: GeneratedData) -> None:
    balance_per_ledger, balance_per_bank = compute_balances(data)
    payload = {
        "seed": data.config.seed,
        "count": data.config.count,
        "start_date": data.config.start_date.isoformat(),
        "num_days": data.config.num_days,
        "ledger_file": LEDGER_FILENAME,
        "bank_file": BANK_FILENAME,
        "totals": {
            "ledger_rows": len(data.ledger_rows),
            "bank_rows": len(data.bank_rows),
            "cases": len(data.cases),
        },
        "balances": {
            "balance_per_ledger": str(balance_per_ledger),
            "balance_per_bank": str(balance_per_bank),
        },
        "cases": [
            {
                "category": case.category.value,
                "ledger_ids": case.ledger_ids,
                "bank_ids": case.bank_ids,
                "note": case.note,
            }
            for case in data.cases
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_all(out_dir: Path, data: GeneratedData) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_ledger_csv(out_dir / LEDGER_FILENAME, data)
    write_bank_csv(out_dir / BANK_FILENAME, data)
    write_answer_key(out_dir / ANSWER_KEY_FILENAME, data)
