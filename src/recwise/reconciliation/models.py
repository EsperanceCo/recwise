"""Data models for the reconciliation statement and suggested journals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ReconcilingItem:
    """A timing difference: present on one side only (ledger or bank)."""

    source: str  # "ledger" or "bank"
    external_id: str
    txn_date: date
    amount: Decimal


@dataclass(frozen=True)
class DiscrepancyItem:
    """A claimed-but-mismatched pair (fuzzy-discrepancy tier): amounts genuinely
    differ between ledger and bank, so this must appear as an explicit
    reconciling residual, not be silently dropped."""

    ledger_id: str
    bank_id: str
    ledger_amount: Decimal
    bank_amount: Decimal
    reason: str

    @property
    def residual(self) -> Decimal:
        """ledger_amount - bank_amount: the dollar gap this discrepancy explains."""
        return self.ledger_amount - self.bank_amount


@dataclass(frozen=True)
class PendingReviewNote:
    """An ambiguous grouping (duplicate-amount or one-to-many) that already
    nets to zero difference, but still needs a human to confirm the pairing
    before it's treated as settled -- per CLAUDE.md, never a coin flip and
    one-to-many matches must be explicit and flagged."""

    tier: str
    ledger_ids: list[str]
    bank_ids: list[str]
    reason: str


@dataclass(frozen=True)
class SuggestedJournal:
    """A suggested (never auto-posted) journal entry for an unrecorded bank item."""

    narrative: str
    debit_account: str
    credit_account: str
    amount: Decimal
    source_bank_id: str


@dataclass
class ReconciliationStatement:
    balance_per_bank: Decimal
    balance_per_ledger: Decimal
    ledger_only_items: list[ReconcilingItem] = field(default_factory=list)
    bank_only_items: list[ReconcilingItem] = field(default_factory=list)
    discrepancy_items: list[DiscrepancyItem] = field(default_factory=list)
    pending_review_notes: list[PendingReviewNote] = field(default_factory=list)
    suggested_journals: list[SuggestedJournal] = field(default_factory=list)

    @property
    def reconciled_balance(self) -> Decimal:
        """balance_per_bank, walked through every reconciling item.

        Must equal balance_per_ledger exactly -- that's the reconciliation
        identity. Ledger-only items are added (present in the books, not
        yet on the bank statement); bank-only items are subtracted (on the
        bank statement, not yet in the books); discrepancy residuals close
        the remaining gap for claimed-but-mismatched pairs.
        """
        total = self.balance_per_bank
        total += sum((item.amount for item in self.ledger_only_items), Decimal("0"))
        total -= sum((item.amount for item in self.bank_only_items), Decimal("0"))
        total += sum((item.residual for item in self.discrepancy_items), Decimal("0"))
        return total
