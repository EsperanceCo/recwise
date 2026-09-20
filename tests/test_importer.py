import json
from decimal import Decimal
from pathlib import Path

import pytest

from recwise.importer import (
    SAMPLE_BANK_MAPPING,
    SAMPLE_LEDGER_MAPPING,
    BankColumnMapping,
    LedgerColumnMapping,
    Source,
    load_bank_statement,
    load_ledger,
)
from recwise.importer import reader as reader_module
from recwise.importer.errors import (
    FileTooLargeError,
    InvalidRowError,
    MissingColumnError,
    UnsupportedFileTypeError,
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def test_load_ledger_matches_answer_key_row_count() -> None:
    answer_key = json.loads((SAMPLE_DIR / "answer_key.json").read_text(encoding="utf-8"))
    transactions = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    assert len(transactions) == answer_key["totals"]["ledger_rows"]


def test_load_bank_statement_matches_answer_key_row_count() -> None:
    answer_key = json.loads((SAMPLE_DIR / "answer_key.json").read_text(encoding="utf-8"))
    transactions = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    assert len(transactions) == answer_key["totals"]["bank_rows"]


def test_all_amounts_are_decimal() -> None:
    transactions = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    for txn in transactions:
        assert isinstance(txn.amount, Decimal)
        assert not isinstance(txn.amount, float)


def test_sources_are_tagged() -> None:
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    assert all(t.source == Source.LEDGER for t in ledger)
    assert all(t.source == Source.BANK for t in bank)


def test_balances_match_answer_key() -> None:
    answer_key = json.loads((SAMPLE_DIR / "answer_key.json").read_text(encoding="utf-8"))
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)

    ledger_balance = sum((t.amount for t in ledger), Decimal("0"))
    bank_balance = sum((t.amount for t in bank), Decimal("0"))

    assert str(ledger_balance) == answer_key["balances"]["balance_per_ledger"]
    assert str(bank_balance) == answer_key["balances"]["balance_per_bank"]


def test_non_ascii_descriptions_survive() -> None:
    transactions = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    assert any(ch in " ".join(t.description for t in transactions) for ch in "əışçöüğ")


def test_normal_exact_case_matches_in_amount_and_id() -> None:
    """Spot-check one planted case end-to-end: a normal_exact pair must have
    equal amounts and the ledger/bank ids the answer key says it should."""
    answer_key = json.loads((SAMPLE_DIR / "answer_key.json").read_text(encoding="utf-8"))
    case = next(c for c in answer_key["cases"] if c["category"] == "normal_exact")

    ledger = {
        t.external_id: t for t in load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    }
    bank = {
        t.external_id: t
        for t in load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    }

    ledger_txn = ledger[case["ledger_ids"][0]]
    bank_txn = bank[case["bank_ids"][0]]
    assert ledger_txn.amount == bank_txn.amount


def test_no_id_column_synthesizes_distinct_ids_not_empty_string(tmp_path: Path) -> None:
    """A file with no id/reference column must never leave every
    Transaction.external_id equal -- that would collapse every row onto
    one key in any {external_id: txn} dict downstream (matching,
    reconciliation, both UIs), corrupting data silently."""
    csv_path = tmp_path / "ledger.csv"
    csv_path.write_text(
        "date,description,amount,account_ref\n"
        "2024-01-01,first,10.00,TEST1\n"
        "2024-01-02,second,20.00,TEST1\n"
        "2024-01-03,third,30.00,TEST1\n",
        encoding="utf-8",
    )
    mapping = LedgerColumnMapping(
        date_col="date",
        date_format="%Y-%m-%d",
        description_col="description",
        amount_col="amount",
        account_col="account_ref",
        # id_col deliberately omitted (defaults to None)
    )
    transactions = load_ledger(csv_path, mapping)
    ids = [t.external_id for t in transactions]
    assert len(set(ids)) == len(ids) == 3
    assert "" not in ids


def test_missing_column_raises_clear_error(tmp_path: Path) -> None:
    bad_csv = tmp_path / "ledger.csv"
    bad_csv.write_text("date,description,amount\n2024-01-01,test,10.00\n", encoding="utf-8")
    mapping = LedgerColumnMapping(
        date_col="date",
        date_format="%Y-%m-%d",
        description_col="description",
        amount_col="amount",
        account_col="account_ref",  # not present in the file
    )
    with pytest.raises(MissingColumnError, match="account_ref"):
        load_ledger(bad_csv, mapping)


def test_bad_date_raises_invalid_row_error(tmp_path: Path) -> None:
    bad_csv = tmp_path / "ledger.csv"
    bad_csv.write_text(
        "date,description,amount,account_ref\nnot-a-date,test,10.00,TEST123\n", encoding="utf-8"
    )
    mapping = LedgerColumnMapping(
        date_col="date",
        date_format="%Y-%m-%d",
        description_col="description",
        amount_col="amount",
        account_col="account_ref",
    )
    with pytest.raises(InvalidRowError) as exc_info:
        load_ledger(bad_csv, mapping)
    assert exc_info.value.row_number == 1


def test_bank_row_with_both_debit_and_credit_raises(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bank.csv"
    bad_csv.write_text(
        "date,description,debit,credit,account_ref\n01/01/2024,test,10.00,5.00,TEST123\n",
        encoding="utf-8",
    )
    mapping = BankColumnMapping(
        date_col="date",
        date_format="%d/%m/%Y",
        description_col="description",
        debit_col="debit",
        credit_col="credit",
        account_col="account_ref",
    )
    with pytest.raises(InvalidRowError, match="both a debit and a credit"):
        load_bank_statement(bad_csv, mapping)


def test_bank_row_with_neither_debit_nor_credit_raises(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bank.csv"
    bad_csv.write_text(
        "date,description,debit,credit,account_ref\n01/01/2024,test,,,TEST123\n", encoding="utf-8"
    )
    mapping = BankColumnMapping(
        date_col="date",
        date_format="%d/%m/%Y",
        description_col="description",
        debit_col="debit",
        credit_col="credit",
        account_col="account_ref",
    )
    with pytest.raises(InvalidRowError, match="neither a debit nor a credit"):
        load_bank_statement(bad_csv, mapping)


def test_unsupported_file_type_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "ledger.txt"
    bad_file.write_text("date,description,amount,account_ref\n", encoding="utf-8")
    with pytest.raises(UnsupportedFileTypeError):
        load_ledger(bad_file, SAMPLE_LEDGER_MAPPING)


def test_oversized_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader_module, "MAX_FILE_SIZE_BYTES", 10)
    big_csv = tmp_path / "ledger.csv"
    big_csv.write_text(
        "date,description,amount,account_ref\n2024-01-01,x,1.00,TEST1\n", encoding="utf-8"
    )
    with pytest.raises(FileTooLargeError):
        load_ledger(big_csv, SAMPLE_LEDGER_MAPPING)


def test_excel_file_round_trips(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    xlsx_path = tmp_path / "ledger.xlsx"
    df = pd.DataFrame(
        [
            {
                "date": "2024-01-05",
                "description": "Ödəniş - test",
                "amount": "1234.56",
                "account_ref": "TEST1",
            },
            {
                "date": "2024-01-06",
                "description": "Mədaxil",
                "amount": "-50.00",
                "account_ref": "TEST2",
            },
        ]
    )
    df.to_excel(xlsx_path, index=False, engine="openpyxl")

    mapping = LedgerColumnMapping(
        date_col="date",
        date_format="%Y-%m-%d",
        description_col="description",
        amount_col="amount",
        account_col="account_ref",
    )
    transactions = load_ledger(xlsx_path, mapping)
    assert len(transactions) == 2
    assert transactions[0].amount == Decimal("1234.56")
    assert transactions[1].amount == Decimal("-50.00")
    assert transactions[0].description == "Ödəniş - test"
