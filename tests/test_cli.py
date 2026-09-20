import json
from pathlib import Path

import pytest

from recwise.cli import main

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def test_cli_end_to_end_on_sample_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "output"
    exit_code = main(
        [
            "--ledger",
            str(SAMPLE_DIR / "ledger.csv"),
            "--bank",
            str(SAMPLE_DIR / "bank_statement.csv"),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0

    expected_files = {
        "matches.csv",
        "ledger_only_items.csv",
        "bank_only_items.csv",
        "discrepancies.csv",
        "pending_review.csv",
        "suggested_journals.csv",
        "reconciliation_summary.csv",
        "audit_log.jsonl",
    }
    assert expected_files <= {p.name for p in out_dir.iterdir()}

    captured = capsys.readouterr()
    assert "Balance per bank" in captured.out
    assert "Balance per ledger" in captured.out
    assert "Reconciled balance" in captured.out


def test_cli_audit_log_has_no_amounts_or_descriptions(tmp_path: Path) -> None:
    out_dir = tmp_path / "output"
    main(
        [
            "--ledger",
            str(SAMPLE_DIR / "ledger.csv"),
            "--bank",
            str(SAMPLE_DIR / "bank_statement.csv"),
            "--out-dir",
            str(out_dir),
        ]
    )
    log_path = out_dir / "audit_log.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines[:20]:
        entry = json.loads(line)
        assert set(entry.keys()) == {
            "timestamp",
            "action",
            "tier",
            "ledger_ids",
            "bank_ids",
            "confidence",
            "actor",
        }


def test_cli_bad_column_mapping_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "output"
    exit_code = main(
        [
            "--ledger",
            str(SAMPLE_DIR / "ledger.csv"),
            "--bank",
            str(SAMPLE_DIR / "bank_statement.csv"),
            "--ledger-amount-col",
            "not_a_real_column",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not_a_real_column" in captured.err
    assert not out_dir.exists()


def test_cli_does_not_modify_input_files(tmp_path: Path) -> None:
    ledger_path = SAMPLE_DIR / "ledger.csv"
    bank_path = SAMPLE_DIR / "bank_statement.csv"
    ledger_before = ledger_path.read_bytes()
    bank_before = bank_path.read_bytes()

    main(
        [
            "--ledger",
            str(ledger_path),
            "--bank",
            str(bank_path),
            "--out-dir",
            str(tmp_path / "output"),
        ]
    )

    assert ledger_path.read_bytes() == ledger_before
    assert bank_path.read_bytes() == bank_before
