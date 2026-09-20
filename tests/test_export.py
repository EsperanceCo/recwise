import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from recwise.export import export_reconciliation, sanitize_cell
from recwise.importer import (
    SAMPLE_BANK_MAPPING,
    SAMPLE_LEDGER_MAPPING,
    load_bank_statement,
    load_ledger,
)
from recwise.importer.models import Source, Transaction
from recwise.matching import match
from recwise.reconciliation import build_statement

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def test_sanitize_cell_prefixes_dangerous_leading_characters() -> None:
    assert sanitize_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert sanitize_cell("+1+1") == "'+1+1"
    assert sanitize_cell("-1+1") == "'-1+1"
    assert sanitize_cell("@SUM(A1)") == "'@SUM(A1)"
    assert sanitize_cell("\tsneaky") == "'\tsneaky"
    assert sanitize_cell("\rsneaky") == "'\rsneaky"


def test_sanitize_cell_leaves_ordinary_text_alone() -> None:
    assert sanitize_cell("Ödəniş - Şəms MMC") == "Ödəniş - Şəms MMC"
    assert sanitize_cell("") == ""
    assert sanitize_cell("Invoice #4521") == "Invoice #4521"


@given(st.text(min_size=0, max_size=50))
def test_sanitize_cell_is_idempotent_and_length_correct(text: str) -> None:
    sanitized = sanitize_cell(text)
    if text.startswith(DANGEROUS_PREFIXES):
        assert sanitized == f"'{text}"
    else:
        assert sanitized == text


def test_export_end_to_end_creates_all_files(tmp_path: Path) -> None:
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)

    export_reconciliation(tmp_path, statement, run.matches)

    expected_files = {
        "matches.csv",
        "ledger_only_items.csv",
        "bank_only_items.csv",
        "discrepancies.csv",
        "pending_review.csv",
        "suggested_journals.csv",
        "reconciliation_summary.csv",
    }
    assert expected_files <= {p.name for p in tmp_path.iterdir()}

    with (tmp_path / "matches.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(run.matches)


def test_export_never_touches_original_input_files(tmp_path: Path) -> None:
    ledger_path = SAMPLE_DIR / "ledger.csv"
    bank_path = SAMPLE_DIR / "bank_statement.csv"
    ledger_before = ledger_path.read_bytes()
    bank_before = bank_path.read_bytes()

    ledger = load_ledger(ledger_path, SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(bank_path, SAMPLE_BANK_MAPPING)
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)
    export_reconciliation(tmp_path, statement, run.matches)

    assert ledger_path.read_bytes() == ledger_before
    assert bank_path.read_bytes() == bank_before


def test_negative_amounts_stay_numeric_not_text_prefixed(tmp_path: Path) -> None:
    """A negative dollar amount must never get the `'` text-sanitization
    prefix -- only text cells are sanitized, per CLAUDE.md."""
    ledger = [
        Transaction(
            source=Source.LEDGER,
            row_number=1,
            external_id="L1",
            txn_date=date(2024, 1, 10),
            description="Unpresented cheque",
            amount=Decimal("-40.00"),
            account_ref="TEST1",
        )
    ]
    bank: list[Transaction] = []
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)
    export_reconciliation(tmp_path, statement, run.matches)

    with (tmp_path / "ledger_only_items.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["amount"] == "-40.00"
    assert not rows[0]["amount"].startswith("'")


def test_malicious_description_is_neutralized_end_to_end(tmp_path: Path) -> None:
    """A crafted description from an untrusted input file must come out
    of the export sanitized, not as a live formula."""
    payload = '=HYPERLINK("http://evil.example/steal","click me")'
    ledger = [
        Transaction(
            source=Source.LEDGER,
            row_number=1,
            external_id="L1",
            txn_date=date(2024, 1, 10),
            description=payload,
            amount=Decimal("10.00"),
            account_ref="TEST1",
        )
    ]
    bank: list[Transaction] = []
    run = match(ledger, bank)
    statement = build_statement(ledger, bank, run)
    export_reconciliation(tmp_path, statement, run.matches)

    with (tmp_path / "ledger_only_items.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["description"] == f"'{payload}"
    assert not rows[0]["description"].startswith("=")
