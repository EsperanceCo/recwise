"""Data models for the synthetic data generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Category(StrEnum):
    """Planted case labels used in the generator's answer key."""

    NORMAL_EXACT = "normal_exact"
    NORMAL_DATE_DIFF = "normal_date_diff"
    DEPOSIT_IN_TRANSIT = "deposit_in_transit"
    UNPRESENTED_CHEQUE = "unpresented_cheque"
    BANK_CHARGE = "bank_charge"
    BANK_INTEREST = "bank_interest"
    DIRECT_DEBIT = "direct_debit"
    DUPLICATE_SAME_DAY = "duplicate_same_day"
    ONE_TO_MANY_DEPOSIT = "one_to_many_deposit"
    ERROR_TRANSPOSED_DIGITS = "error_transposed_digits"
    ERROR_WRONG_AMOUNT = "error_wrong_amount"
    ERROR_WRONG_DATE = "error_wrong_date"


@dataclass(frozen=True)
class LedgerRow:
    """A single cash book (ledger) entry.

    `amount` is signed per the convention in recwise.money: positive = debit
    (cash inflow), negative = credit (cash outflow).
    """

    id: str
    txn_date: date
    description: str
    amount: Decimal
    account_ref: str


@dataclass(frozen=True)
class BankRow:
    """A single bank statement entry with separate debit/credit columns.

    Exactly one of `debit` / `credit` is non-None on any real row; the other
    is None (written as an empty CSV cell).
    """

    id: str
    txn_date: date
    description: str
    debit: Decimal | None
    credit: Decimal | None
    account_ref: str


@dataclass(frozen=True)
class PlantedCase:
    """One planted scenario in the answer key, linking ledger and bank rows."""

    category: Category
    ledger_ids: list[str] = field(default_factory=list)
    bank_ids: list[str] = field(default_factory=list)
    note: str = ""
