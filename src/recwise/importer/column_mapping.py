"""Explicit column mappings: how a source file's columns map onto a Transaction.

Nothing here is guessed. A caller states which column is the date, which is
the amount, and what date format that column uses; if a named column is
missing from the file, loading fails with MissingColumnError rather than
silently skipping data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LedgerColumnMapping:
    """Column mapping for a cash-book style file: one signed amount column."""

    date_col: str
    date_format: str
    description_col: str
    amount_col: str
    account_col: str
    id_col: str | None = None

    def required_columns(self) -> list[str]:
        cols = [self.date_col, self.description_col, self.amount_col, self.account_col]
        if self.id_col is not None:
            cols.append(self.id_col)
        return cols


@dataclass(frozen=True)
class BankColumnMapping:
    """Column mapping for a bank-statement style file: separate debit/credit columns."""

    date_col: str
    date_format: str
    description_col: str
    debit_col: str
    credit_col: str
    account_col: str
    id_col: str | None = None

    def required_columns(self) -> list[str]:
        cols = [
            self.date_col,
            self.description_col,
            self.debit_col,
            self.credit_col,
            self.account_col,
        ]
        if self.id_col is not None:
            cols.append(self.id_col)
        return cols


# Mappings matching recwise.synth's own output (sample_data/), for
# convenience and as a worked example of how to build a mapping.
SAMPLE_LEDGER_MAPPING = LedgerColumnMapping(
    date_col="date",
    date_format="%Y-%m-%d",
    description_col="description",
    amount_col="amount",
    account_col="account_ref",
    id_col="id",
)

SAMPLE_BANK_MAPPING = BankColumnMapping(
    date_col="date",
    date_format="%d/%m/%Y",
    description_col="description",
    debit_col="debit",
    credit_col="credit",
    account_col="account_ref",
    id_col="id",
)
