"""Canonical shape that both ledger and bank rows normalize into."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Source(StrEnum):
    LEDGER = "ledger"
    BANK = "bank"


@dataclass(frozen=True)
class Transaction:
    """A single imported transaction, already normalized.

    `amount` is signed per the convention in recwise.money: positive = debit
    (cash inflow), negative = credit (cash outflow) -- the same sign-space
    for both ledger and bank transactions, so they can be compared directly.
    """

    source: Source
    row_number: int  # 1-indexed, header excluded; for error messages and audit trail
    external_id: str
    txn_date: date
    description: str
    amount: Decimal
    account_ref: str
