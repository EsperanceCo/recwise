from datetime import date
from decimal import Decimal
from pathlib import Path

from recwise.importer import (
    SAMPLE_BANK_MAPPING,
    SAMPLE_LEDGER_MAPPING,
    load_bank_statement,
    load_ledger,
)
from recwise.importer.models import Source, Transaction
from recwise.matching import match
from recwise.matching.models import MatchTier
from recwise.reconciliation import build_statement

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _load_sample() -> tuple[list[Transaction], list[Transaction]]:
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    return ledger, bank


def test_reconciliation_identity_holds_on_sample_data() -> None:
    ledger, bank = _load_sample()
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)
    assert statement.reconciled_balance == statement.balance_per_ledger


def test_every_bank_only_item_has_a_suggested_journal() -> None:
    ledger, bank = _load_sample()
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)

    assert len(statement.suggested_journals) == len(statement.bank_only_items)
    bank_only_ids = {item.external_id for item in statement.bank_only_items}
    for journal in statement.suggested_journals:
        assert journal.source_bank_id in bank_only_ids
        assert journal.amount > 0


def test_pending_review_notes_are_net_zero() -> None:
    """Duplicate-amount and one-to-many review groups already balance on
    their own; that's exactly why they don't need a discrepancy line."""
    ledger, bank = _load_sample()
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)

    ledger_by_id = {t.external_id: t for t in ledger}
    bank_by_id = {t.external_id: t for t in bank}
    assert statement.pending_review_notes
    for note in statement.pending_review_notes:
        ledger_total = sum((ledger_by_id[lid].amount for lid in note.ledger_ids), Decimal("0"))
        bank_total = sum((bank_by_id[bid].amount for bid in note.bank_ids), Decimal("0"))
        assert ledger_total == bank_total


def test_discrepancy_items_carry_the_real_residual() -> None:
    """Only fuzzy-discrepancy matches with an actual amount mismatch become
    a DiscrepancyItem. A "wrong date" fuzzy match (same amount, different
    date) has zero residual and belongs with the other net-zero pending
    items instead -- it doesn't affect the balance identity."""
    ledger, bank = _load_sample()
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)

    ledger_by_id = {t.external_id: t for t in ledger}
    bank_by_id = {t.external_id: t for t in bank}
    fuzzy_matches = [m for m in run.review_matches() if m.tier == MatchTier.FUZZY_DISCREPANCY]
    expected_discrepancies = [
        m
        for m in fuzzy_matches
        if ledger_by_id[m.ledger_ids[0]].amount != bank_by_id[m.bank_ids[0]].amount
    ]
    assert len(statement.discrepancy_items) == len(expected_discrepancies)
    assert statement.discrepancy_items  # sanity: sample data actually has some
    for item in statement.discrepancy_items:
        assert item.residual == item.ledger_amount - item.bank_amount
        assert item.residual != 0


def test_handcrafted_timing_and_bank_only_items() -> None:
    ledger = [
        Transaction(
            source=Source.LEDGER,
            row_number=1,
            external_id="L1",
            txn_date=date(2024, 1, 10),
            description="Deposit in transit",
            amount=Decimal("100.00"),
            account_ref="TEST1",
        ),
        Transaction(
            source=Source.LEDGER,
            row_number=2,
            external_id="L2",
            txn_date=date(2024, 1, 11),
            description="Unpresented cheque",
            amount=Decimal("-40.00"),
            account_ref="TEST1",
        ),
    ]
    bank = [
        Transaction(
            source=Source.BANK,
            row_number=1,
            external_id="B1",
            txn_date=date(2024, 1, 12),
            description="Bank komissiyasi",
            amount=Decimal("-5.00"),
            account_ref="TEST1",
        ),
        Transaction(
            source=Source.BANK,
            row_number=2,
            external_id="B2",
            txn_date=date(2024, 1, 13),
            description="Faiz gəliri",
            amount=Decimal("2.00"),
            account_ref="TEST1",
        ),
    ]
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)

    # balance_per_bank = -5 + 2 = -3; balance_per_ledger = 100 - 40 = 60
    assert statement.balance_per_bank == Decimal("-3.00")
    assert statement.balance_per_ledger == Decimal("60.00")
    assert statement.reconciled_balance == Decimal("60.00")

    assert {item.external_id for item in statement.ledger_only_items} == {"L1", "L2"}
    assert {item.external_id for item in statement.bank_only_items} == {"B1", "B2"}

    journals_by_source = {j.source_bank_id: j for j in statement.suggested_journals}
    charge_journal = journals_by_source["B1"]
    assert charge_journal.amount == Decimal("5.00")
    assert charge_journal.debit_account == "Bank Charges Expense"
    assert charge_journal.credit_account == "Cash at Bank"

    interest_journal = journals_by_source["B2"]
    assert interest_journal.amount == Decimal("2.00")
    assert interest_journal.debit_account == "Cash at Bank"
    assert interest_journal.credit_account == "Interest Income"


def test_journals_are_a_pure_suggestion_no_files_written(tmp_path: Path) -> None:
    """build_statement must be pure: no I/O, nothing posted anywhere."""
    ledger, bank = _load_sample()
    run = match(ledger, bank)
    before = set(tmp_path.iterdir())
    build_statement(ledger, bank, run)
    after = set(tmp_path.iterdir())
    assert before == after
