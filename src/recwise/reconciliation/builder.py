"""Turn a MatchRun into a balanced ReconciliationStatement with suggested journals.

Never auto-posts anything: journals are suggestions only, and every
ambiguous or discrepant item is surfaced for a human decision rather than
silently resolved.
"""

from __future__ import annotations

from decimal import Decimal

from recwise.importer.models import Transaction
from recwise.matching.models import MatchRun, MatchTier
from recwise.reconciliation.models import (
    DiscrepancyItem,
    PendingReviewNote,
    ReconciliationStatement,
    ReconcilingItem,
    SuggestedJournal,
)

# Generic placeholder GL accounts. These are a starting point for the
# accountant to re-code, never a final classification -- the tool has no
# chart-of-accounts configuration to draw from.
CASH_ACCOUNT = "Cash at Bank"
BANK_CHARGE_ACCOUNT = "Bank Charges Expense"
INTEREST_ACCOUNT = "Interest Income"
UNCLASSIFIED_DEBIT_ACCOUNT = "Sundry/Unclassified Expense"


def _suggest_journal_for_bank_only(txn: Transaction) -> SuggestedJournal:
    """Suggest a journal for a bank-only item. `amount` is signed per
    recwise.money: positive = credit (money in), negative = debit (money out).
    """
    narrative = f"Per bank statement, not yet recorded in ledger: {txn.description}"
    if txn.amount >= 0:
        # Bank credit not in the books: likely interest or another credit.
        return SuggestedJournal(
            narrative=narrative,
            debit_account=CASH_ACCOUNT,
            credit_account=INTEREST_ACCOUNT,
            amount=txn.amount,
            source_bank_id=txn.external_id,
        )
    # Bank debit not in the books: likely a charge, fee, or direct debit.
    # We can't tell a bank fee from an unclassified direct debit from the
    # amount alone, so this defaults to the more generic account.
    debit_account = (
        BANK_CHARGE_ACCOUNT if "komis" in txn.description.lower() else UNCLASSIFIED_DEBIT_ACCOUNT
    )
    return SuggestedJournal(
        narrative=narrative,
        debit_account=debit_account,
        credit_account=CASH_ACCOUNT,
        amount=-txn.amount,
        source_bank_id=txn.external_id,
    )


def build_statement(
    ledger: list[Transaction], bank: list[Transaction], run: MatchRun
) -> ReconciliationStatement:
    balance_per_bank = sum((t.amount for t in bank), Decimal("0"))
    balance_per_ledger = sum((t.amount for t in ledger), Decimal("0"))

    ledger_only_items = [
        ReconcilingItem(
            source="ledger",
            external_id=t.external_id,
            txn_date=t.txn_date,
            amount=t.amount,
            description=t.description,
        )
        for t in run.unmatched_ledger
    ]
    bank_only_items = [
        ReconcilingItem(
            source="bank",
            external_id=t.external_id,
            txn_date=t.txn_date,
            amount=t.amount,
            description=t.description,
        )
        for t in run.unmatched_bank
    ]
    suggested_journals = [_suggest_journal_for_bank_only(t) for t in run.unmatched_bank]

    ledger_by_id = {t.external_id: t for t in ledger}
    bank_by_id = {t.external_id: t for t in bank}

    discrepancy_items: list[DiscrepancyItem] = []
    pending_review_notes: list[PendingReviewNote] = []
    for m in run.review_matches():
        if m.tier == MatchTier.FUZZY_DISCREPANCY:
            ledger_txn = ledger_by_id[m.ledger_ids[0]]
            bank_txn = bank_by_id[m.bank_ids[0]]
            discrepancy_items.append(
                DiscrepancyItem(
                    ledger_id=ledger_txn.external_id,
                    bank_id=bank_txn.external_id,
                    ledger_amount=ledger_txn.amount,
                    bank_amount=bank_txn.amount,
                    ledger_description=ledger_txn.description,
                    bank_description=bank_txn.description,
                    reason=m.reason,
                )
            )
        else:
            pending_review_notes.append(
                PendingReviewNote(
                    tier=m.tier.value,
                    ledger_ids=m.ledger_ids,
                    bank_ids=m.bank_ids,
                    reason=m.reason,
                )
            )

    return ReconciliationStatement(
        balance_per_bank=balance_per_bank,
        balance_per_ledger=balance_per_ledger,
        ledger_only_items=ledger_only_items,
        bank_only_items=bank_only_items,
        discrepancy_items=discrepancy_items,
        pending_review_notes=pending_review_notes,
        suggested_journals=suggested_journals,
    )
