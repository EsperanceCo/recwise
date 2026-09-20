"""Load a ledger or bank statement file into a list of Transaction objects."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.importer.errors import InvalidRowError, MissingColumnError
from recwise.importer.models import Source, Transaction
from recwise.importer.normalize import clean_description, parse_txn_date
from recwise.importer.reader import read_table
from recwise.money import InvalidAmountError, bank_amount_to_signed, parse_amount


def _check_required_columns(df: pd.DataFrame, required: list[str], filename: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise MissingColumnError(
            f"{filename}: missing column(s) {missing}, found {list(df.columns)}"
        )


def load_ledger(path: Path, mapping: LedgerColumnMapping) -> list[Transaction]:
    path = Path(path)
    df = read_table(path)
    _check_required_columns(df, mapping.required_columns(), path.name)

    transactions: list[Transaction] = []
    for i, row in enumerate(df.to_dict(orient="records"), start=1):
        try:
            txn_date = parse_txn_date(row[mapping.date_col], mapping.date_format)
            amount = parse_amount(row[mapping.amount_col])
        except (ValueError, InvalidAmountError) as exc:
            raise InvalidRowError(i, str(exc)) from exc

        transactions.append(
            Transaction(
                source=Source.LEDGER,
                row_number=i,
                external_id=row[mapping.id_col] if mapping.id_col else f"row-{i}",
                txn_date=txn_date,
                description=clean_description(row[mapping.description_col]),
                amount=amount,
                account_ref=row[mapping.account_col].strip(),
            )
        )
    return transactions


def load_bank_statement(path: Path, mapping: BankColumnMapping) -> list[Transaction]:
    path = Path(path)
    df = read_table(path)
    _check_required_columns(df, mapping.required_columns(), path.name)

    transactions: list[Transaction] = []
    for i, row in enumerate(df.to_dict(orient="records"), start=1):
        try:
            txn_date = parse_txn_date(row[mapping.date_col], mapping.date_format)
            debit_raw = row[mapping.debit_col].strip()
            credit_raw = row[mapping.credit_col].strip()
            debit = parse_amount(debit_raw) if debit_raw else None
            credit = parse_amount(credit_raw) if credit_raw else None
            if debit is None and credit is None:
                raise ValueError("row has neither a debit nor a credit amount")
            if debit is not None and credit is not None:
                raise ValueError("row has both a debit and a credit amount; expected exactly one")
            amount = bank_amount_to_signed(debit, credit)
        except (ValueError, InvalidAmountError) as exc:
            raise InvalidRowError(i, str(exc)) from exc

        transactions.append(
            Transaction(
                source=Source.BANK,
                row_number=i,
                external_id=row[mapping.id_col] if mapping.id_col else f"row-{i}",
                txn_date=txn_date,
                description=clean_description(row[mapping.description_col]),
                amount=amount,
                account_ref=row[mapping.account_col].strip(),
            )
        )
    return transactions
