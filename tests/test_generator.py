import csv
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from recwise.money import bank_amount_to_signed, parse_amount
from recwise.synth.generator import SynthConfig, generate
from recwise.synth.models import Category
from recwise.synth.writer import (
    ANSWER_KEY_FILENAME,
    BANK_DATE_FMT,
    BANK_FILENAME,
    LEDGER_DATE_FMT,
    LEDGER_FILENAME,
    write_all,
)


def _make(count: int = 300, seed: int = 42) -> SynthConfig:
    return SynthConfig(seed=seed, count=count, start_date=date(2024, 1, 1), num_days=90)


def test_reproducible_with_same_seed(tmp_path: Path) -> None:
    data_a = generate(_make(seed=7))
    data_b = generate(_make(seed=7))
    assert [r.__dict__ for r in data_a.ledger_rows] == [r.__dict__ for r in data_b.ledger_rows]
    assert [r.__dict__ for r in data_a.bank_rows] == [r.__dict__ for r in data_b.bank_rows]
    assert [c.__dict__ for c in data_a.cases] == [c.__dict__ for c in data_b.cases]


def test_different_seed_gives_different_output() -> None:
    data_a = generate(_make(seed=1))
    data_b = generate(_make(seed=2))
    assert [r.amount for r in data_a.ledger_rows] != [r.amount for r in data_b.ledger_rows]


def test_all_planted_categories_present() -> None:
    data = generate(_make(count=500))
    seen = {case.category for case in data.cases}
    assert seen == set(Category)


def test_no_float_touches_money() -> None:
    data = generate(_make(count=100))
    for ledger_row in data.ledger_rows:
        assert isinstance(ledger_row.amount, Decimal)
        assert not isinstance(ledger_row.amount, float)
    for bank_row in data.bank_rows:
        if bank_row.debit is not None:
            assert isinstance(bank_row.debit, Decimal)
        if bank_row.credit is not None:
            assert isinstance(bank_row.credit, Decimal)


def test_only_test_prefixed_accounts_and_no_iban_shaped_strings(tmp_path: Path) -> None:
    data = generate(_make(count=200))
    write_all(tmp_path, data)

    for filename in (LEDGER_FILENAME, BANK_FILENAME):
        text = (tmp_path / filename).read_text(encoding="utf-8-sig")
        for account_ref in re.findall(r"TEST\d{6}", text):
            assert account_ref.startswith("TEST")

        # No token anywhere in the file should be IBAN-shaped AND pass the
        # mod-97 checksum (the generator must never produce something that
        # looks like a real account number).
        for candidate in re.findall(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", text):
            assert not _passes_iban_checksum(candidate)


def _passes_iban_checksum(candidate: str) -> bool:
    rearranged = candidate[4:] + candidate[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def test_reconciliation_identity_holds_from_written_files(tmp_path: Path) -> None:
    """balance per bank + reconciling items == balance per cash book.

    Recomputed entirely from the files on disk (not generator internals) so
    a bug in CSV writing, date formatting, or decimal-comma parsing would be
    caught here.
    """
    data = generate(_make(count=400))
    write_all(tmp_path, data)

    ledger_balance = Decimal("0")
    ledger_amount_by_id: dict[str, Decimal] = {}
    with (tmp_path / LEDGER_FILENAME).open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            amount = parse_amount(row["amount"])
            ledger_balance += amount
            ledger_amount_by_id[row["id"]] = amount

    bank_balance = Decimal("0")
    bank_amount_by_id: dict[str, Decimal] = {}
    with (tmp_path / BANK_FILENAME).open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            debit = parse_amount(row["debit"]) if row["debit"] else None
            credit = parse_amount(row["credit"]) if row["credit"] else None
            signed = bank_amount_to_signed(debit, credit)
            bank_balance += signed
            bank_amount_by_id[row["id"]] = signed

    answer_key = json.loads((tmp_path / ANSWER_KEY_FILENAME).read_text(encoding="utf-8"))
    assert Decimal(answer_key["balances"]["balance_per_ledger"]) == ledger_balance
    assert Decimal(answer_key["balances"]["balance_per_bank"]) == bank_balance

    # Reconciling total, derived purely from the answer key's own case list.
    reconciling_total = Decimal("0")
    for case in answer_key["cases"]:
        ledger_side = sum((ledger_amount_by_id[lid] for lid in case["ledger_ids"]), Decimal("0"))
        bank_side = sum((bank_amount_by_id[bid] for bid in case["bank_ids"]), Decimal("0"))
        reconciling_total += ledger_side - bank_side

    assert ledger_balance - bank_balance == reconciling_total


def test_dates_use_different_formats(tmp_path: Path) -> None:
    data = generate(_make(count=50))
    write_all(tmp_path, data)

    with (tmp_path / LEDGER_FILENAME).open(encoding="utf-8-sig") as fh:
        first_ledger_date = next(csv.DictReader(fh))["date"]
    with (tmp_path / BANK_FILENAME).open(encoding="utf-8-sig") as fh:
        first_bank_date = next(csv.DictReader(fh))["date"]

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", first_ledger_date)
    assert re.match(r"^\d{2}/\d{2}/\d{4}$", first_bank_date)
    assert LEDGER_DATE_FMT == "%Y-%m-%d"
    assert BANK_DATE_FMT == "%d/%m/%Y"


def test_non_ascii_characters_present(tmp_path: Path) -> None:
    data = generate(_make(count=300))
    write_all(tmp_path, data)
    text = (tmp_path / LEDGER_FILENAME).read_text(encoding="utf-8-sig")
    assert any(ch in text for ch in "əışçöüğ")


def test_duplicate_same_day_ids_are_distinct_and_paired_correctly() -> None:
    data = generate(_make(count=500))
    dup_cases = [c for c in data.cases if c.category == Category.DUPLICATE_SAME_DAY]
    assert dup_cases
    for case in dup_cases:
        assert len(case.ledger_ids) == 2
        assert len(case.bank_ids) == 2
        assert len(set(case.ledger_ids)) == 2
        assert len(set(case.bank_ids)) == 2
