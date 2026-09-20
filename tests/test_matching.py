import json
from pathlib import Path
from typing import Any

from recwise.importer import (
    SAMPLE_BANK_MAPPING,
    SAMPLE_LEDGER_MAPPING,
    load_bank_statement,
    load_ledger,
)
from recwise.importer.models import Transaction
from recwise.matching import MatchStatus, MatchTier, match
from recwise.matching.audit import AuditAction, append_entries, entries_from_match_run, read_entries

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _load_sample() -> tuple[list[Transaction], list[Transaction], dict[str, Any]]:
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    answer_key: dict[str, Any] = json.loads(
        (SAMPLE_DIR / "answer_key.json").read_text(encoding="utf-8")
    )
    return ledger, bank, answer_key


def _cases_by_category(answer_key: dict[str, Any], category: str) -> list[dict[str, Any]]:
    return [c for c in answer_key["cases"] if c["category"] == category]


def test_matching_is_deterministic() -> None:
    ledger, bank, _ = _load_sample()
    run_a = match(ledger, bank)
    run_b = match(ledger, bank)
    assert [(m.tier, m.status, m.ledger_ids, m.bank_ids) for m in run_a.matches] == [
        (m.tier, m.status, m.ledger_ids, m.bank_ids) for m in run_b.matches
    ]
    assert [t.external_id for t in run_a.unmatched_ledger] == [
        t.external_id for t in run_b.unmatched_ledger
    ]
    assert [t.external_id for t in run_a.unmatched_bank] == [
        t.external_id for t in run_b.unmatched_bank
    ]


def test_normal_exact_cases_are_auto_matched_correctly() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    auto_by_pair = {
        (tuple(m.ledger_ids), tuple(m.bank_ids))
        for m in run.auto_matches()
        if m.tier == MatchTier.EXACT
    }
    for case in _cases_by_category(answer_key, "normal_exact"):
        assert (tuple(case["ledger_ids"]), tuple(case["bank_ids"])) in auto_by_pair


def test_normal_date_diff_cases_are_auto_matched_correctly() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    auto_by_pair = {
        (tuple(m.ledger_ids), tuple(m.bank_ids))
        for m in run.auto_matches()
        if m.tier == MatchTier.DATE_WINDOW
    }
    for case in _cases_by_category(answer_key, "normal_date_diff"):
        assert (tuple(case["ledger_ids"]), tuple(case["bank_ids"])) in auto_by_pair


def test_zero_false_positives_in_auto_tier() -> None:
    """Every AUTO match's ids must correspond exactly to a real answer-key
    case with the same ledger/bank ids. This is the hard requirement:
    false positives in the auto-match tier must be zero."""
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)

    real_pairs = {
        (tuple(sorted(c["ledger_ids"])), tuple(sorted(c["bank_ids"])))
        for c in answer_key["cases"]
        if c["ledger_ids"] and c["bank_ids"]
    }
    for m in run.auto_matches():
        pair = (tuple(sorted(m.ledger_ids)), tuple(sorted(m.bank_ids)))
        assert pair in real_pairs, f"false positive: {m}"


def test_duplicate_same_day_goes_to_review_not_auto() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    auto_ledger_ids = {lid for m in run.auto_matches() for lid in m.ledger_ids}
    auto_bank_ids = {bid for m in run.auto_matches() for bid in m.bank_ids}

    review_pairs = [
        (frozenset(m.ledger_ids), frozenset(m.bank_ids))
        for m in run.review_matches()
        if m.tier == MatchTier.EXACT
    ]
    for case in _cases_by_category(answer_key, "duplicate_same_day"):
        for lid in case["ledger_ids"]:
            assert lid not in auto_ledger_ids
        for bid in case["bank_ids"]:
            assert bid not in auto_bank_ids
        assert (frozenset(case["ledger_ids"]), frozenset(case["bank_ids"])) in review_pairs


def test_timing_differences_remain_unmatched() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    unmatched_ledger_ids = {t.external_id for t in run.unmatched_ledger}
    unmatched_bank_ids = {t.external_id for t in run.unmatched_bank}

    for case in _cases_by_category(answer_key, "deposit_in_transit") + _cases_by_category(
        answer_key, "unpresented_cheque"
    ):
        assert case["ledger_ids"][0] in unmatched_ledger_ids

    for category in ("bank_charge", "bank_interest", "direct_debit"):
        for case in _cases_by_category(answer_key, category):
            assert case["bank_ids"][0] in unmatched_bank_ids


def test_one_to_many_cases_are_review_not_auto() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    one_to_many_review = [m for m in run.matches if m.tier == MatchTier.ONE_TO_MANY]
    assert one_to_many_review
    assert all(m.status == MatchStatus.REVIEW for m in one_to_many_review)

    review_pairs = {(frozenset(m.ledger_ids), frozenset(m.bank_ids)) for m in one_to_many_review}
    found = 0
    for case in _cases_by_category(answer_key, "one_to_many_deposit"):
        pair = (frozenset(case["ledger_ids"]), frozenset(case["bank_ids"]))
        if pair in review_pairs:
            found += 1
    # Every one-to-many case must be found unambiguously given how the
    # synth generator constructs them (unique account_ref per case).
    assert found == len(_cases_by_category(answer_key, "one_to_many_deposit"))


def test_error_cases_never_auto_matched() -> None:
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    auto_ledger_ids = {lid for m in run.auto_matches() for lid in m.ledger_ids}
    auto_bank_ids = {bid for m in run.auto_matches() for bid in m.bank_ids}

    for category in ("error_transposed_digits", "error_wrong_amount", "error_wrong_date"):
        for case in _cases_by_category(answer_key, category):
            assert case["ledger_ids"][0] not in auto_ledger_ids
            assert case["bank_ids"][0] not in auto_bank_ids


def test_recall_on_clean_matches_is_high() -> None:
    """Precision/recall reporting against the answer key, per CLAUDE.md."""
    ledger, bank, answer_key = _load_sample()
    run = match(ledger, bank)
    auto_pairs = {(tuple(m.ledger_ids), tuple(m.bank_ids)) for m in run.auto_matches()}
    expected_cases = _cases_by_category(answer_key, "normal_exact") + _cases_by_category(
        answer_key, "normal_date_diff"
    )
    expected_pairs = {(tuple(c["ledger_ids"]), tuple(c["bank_ids"])) for c in expected_cases}
    recall = len(expected_pairs & auto_pairs) / len(expected_pairs)
    assert recall == 1.0


def test_audit_log_round_trips(tmp_path: Path) -> None:
    ledger, bank, _ = _load_sample()
    run = match(ledger, bank)
    entries = entries_from_match_run(run, timestamp="2024-01-01T00:00:00+00:00")
    assert len(entries) == len(run.matches)
    assert all(e.action in (AuditAction.AUTO_MATCH, AuditAction.REVIEW_SUGGESTED) for e in entries)

    log_path = tmp_path / "audit.jsonl"
    append_entries(log_path, entries)
    read_back = read_entries(log_path)
    assert len(read_back) == len(entries)
    assert read_back[0]["timestamp"] == "2024-01-01T00:00:00+00:00"

    # Log entries must never leak descriptions -- only ids, tiers, and scores.
    raw_text = log_path.read_text(encoding="utf-8")
    for txn in ledger[:5]:
        assert txn.description not in raw_text
