import math
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from recwise.analytics.benford import Conformity, analyze, expected_proportions, leading_digit
from recwise.analytics.cli import main
from recwise.importer.models import Source, Transaction

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _txn(amount: str, external_id: str = "T1") -> Transaction:
    return Transaction(
        source=Source.LEDGER,
        row_number=1,
        external_id=external_id,
        txn_date=date(2024, 1, 1),
        description="test",
        amount=Decimal(amount),
        account_ref="TEST1",
    )


def test_expected_proportions_sum_to_one_and_match_known_values() -> None:
    proportions = expected_proportions()
    assert set(proportions.keys()) == set(range(1, 10))
    assert math.isclose(sum(proportions.values()), 1.0, rel_tol=1e-9)
    assert math.isclose(proportions[1], 0.30103, rel_tol=1e-4)
    assert math.isclose(proportions[9], 0.04576, rel_tol=1e-3)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("123.45", 1),
        ("999.00", 9),
        ("0.05", 5),
        ("-45.60", 4),
        ("100.00", 1),
        ("0.00", None),
        ("5", 5),
    ],
)
def test_leading_digit(amount: str, expected: int | None) -> None:
    assert leading_digit(Decimal(amount)) == expected


def test_analyze_empty_population() -> None:
    result = analyze([])
    assert result.sample_size == 0
    assert result.sufficient_sample is False
    assert result.conformity == Conformity.NONCONFORMITY


def test_analyze_excludes_zero_amounts() -> None:
    transactions = [_txn("0.00", "T1"), _txn("100.00", "T2")]
    result = analyze(transactions)
    assert result.sample_size == 1


def test_analyze_ignores_sign() -> None:
    result = analyze([_txn("-500.00", "T1")])
    stat = next(s for s in result.digit_stats if s.digit == 5)
    assert stat.observed_count == 1


def test_analyze_flags_insufficient_sample() -> None:
    result = analyze([_txn("100.00", f"T{i}") for i in range(50)])
    assert result.sample_size == 50
    assert result.sufficient_sample is False


def test_analyze_engineered_conforming_population_is_close_conformity() -> None:
    """Build a population whose leading-digit counts exactly match Benford's
    Law (for N=10000) and confirm the classifier reports close conformity --
    proving it correctly recognizes the good case, not just nonconformity."""
    n = 10000
    expected = expected_proportions()
    transactions = []
    i = 0
    for digit, proportion in expected.items():
        count = round(proportion * n)
        for _ in range(count):
            transactions.append(_txn(f"{digit}00.00", f"T{i}"))
            i += 1

    result = analyze(transactions)
    assert result.sufficient_sample is True
    assert result.mean_absolute_deviation < 0.006
    assert result.conformity == Conformity.CLOSE


def test_analyze_uniform_random_sample_data_is_nonconformity() -> None:
    """recwise.synth draws amounts uniformly at random, which does not
    follow Benford's Law -- this is the expected, correct result, not a
    bug: proof the analysis actually discriminates real distributions."""
    from recwise.importer import SAMPLE_LEDGER_MAPPING, load_ledger

    transactions = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    result = analyze(transactions)
    assert result.sample_size == 1000
    assert result.sufficient_sample is True
    assert result.conformity == Conformity.NONCONFORMITY


def test_digit_stats_observed_proportions_sum_to_one() -> None:
    from recwise.importer import SAMPLE_LEDGER_MAPPING, load_ledger

    transactions = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    result = analyze(transactions)
    total = sum(stat.observed_proportion for stat in result.digit_stats)
    assert math.isclose(total, 1.0, rel_tol=1e-9)


def test_cli_runs_against_sample_ledger(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--file", str(SAMPLE_DIR / "ledger.csv"), "--kind", "ledger"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Sample size: 1000" in captured.out
    assert "Mean absolute deviation" in captured.out
    assert "Conformity" in captured.out


def test_cli_runs_against_sample_bank(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "--file",
            str(SAMPLE_DIR / "bank_statement.csv"),
            "--kind",
            "bank",
            "--date-format",
            "%d/%m/%Y",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Sample size" in captured.out


def test_cli_bad_file_fails_clearly(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    exit_code = main(["--file", str(tmp_path / "does_not_exist.csv"), "--kind", "ledger"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err
