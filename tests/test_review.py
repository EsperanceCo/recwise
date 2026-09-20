import json
from pathlib import Path

import pytest

from recwise.importer import (
    SAMPLE_BANK_MAPPING,
    SAMPLE_LEDGER_MAPPING,
    load_bank_statement,
    load_ledger,
)
from recwise.importer.models import Transaction
from recwise.reconciliation import build_statement
from recwise.review import ManualMatchError, load_session, manual_match, reject
from recwise.review.service import accept, save_session
from recwise.review.state import Decision, ReviewState, match_key

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _load_sample() -> tuple[list[Transaction], list[Transaction]]:
    ledger = load_ledger(SAMPLE_DIR / "ledger.csv", SAMPLE_LEDGER_MAPPING)
    bank = load_bank_statement(SAMPLE_DIR / "bank_statement.csv", SAMPLE_BANK_MAPPING)
    return ledger, bank


def test_new_session_has_all_review_matches_pending(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    assert state.pending_matches() == state.run.review_matches()


def test_accept_moves_match_out_of_pending(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    target = state.run.review_matches()[0]

    accept(tmp_path, state, target)

    assert state.decision_for(target) == Decision.ACCEPTED
    assert target not in state.pending_matches()


def test_accepted_match_appears_in_confirmed_snapshot(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    target = state.run.review_matches()[0]
    accept(tmp_path, state, target)

    snapshot = state.to_match_run(ledger, bank)
    assert target in snapshot.matches
    for lid in target.ledger_ids:
        assert lid not in {t.external_id for t in snapshot.unmatched_ledger}
    for bid in target.bank_ids:
        assert bid not in {t.external_id for t in snapshot.unmatched_bank}


def test_reject_returns_ids_to_unmatched(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    target = state.run.review_matches()[0]
    reject(tmp_path, state, target)

    snapshot = state.to_match_run(ledger, bank)
    unmatched_ledger_ids = {t.external_id for t in snapshot.unmatched_ledger}
    unmatched_bank_ids = {t.external_id for t in snapshot.unmatched_bank}
    for lid in target.ledger_ids:
        assert lid in unmatched_ledger_ids
    for bid in target.bank_ids:
        assert bid in unmatched_bank_ids


def test_reconciliation_identity_holds_after_accept_and_reject(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    reviews = state.run.review_matches()
    accept(tmp_path, state, reviews[0])
    reject(tmp_path, state, reviews[1])
    reject(tmp_path, state, reviews[2])

    snapshot = state.to_match_run(ledger, bank)
    statement = build_statement(ledger, bank, snapshot)
    assert statement.reconciled_balance == statement.balance_per_ledger


def test_manual_match_between_two_unmatched_items(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    ledger_id = state.run.unmatched_ledger[0].external_id
    bank_id = state.run.unmatched_bank[0].external_id

    m = manual_match(tmp_path, state, ledger_id, bank_id)

    assert m.ledger_ids == [ledger_id]
    assert m.bank_ids == [bank_id]
    snapshot = state.to_match_run(ledger, bank)
    assert m in snapshot.matches


def test_manual_match_with_mismatched_amounts_still_balances(tmp_path: Path) -> None:
    """A human can force-pair two transactions whose amounts differ; the
    reconciliation statement must still balance via a discrepancy line."""
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    ledger_txn = state.run.unmatched_ledger[0]
    bank_txn = next(t for t in state.run.unmatched_bank if t.amount != ledger_txn.amount)

    manual_match(tmp_path, state, ledger_txn.external_id, bank_txn.external_id)

    snapshot = state.to_match_run(ledger, bank)
    statement = build_statement(ledger, bank, snapshot)
    assert statement.reconciled_balance == statement.balance_per_ledger
    residuals = {(d.ledger_id, d.bank_id) for d in statement.discrepancy_items}
    assert (ledger_txn.external_id, bank_txn.external_id) in residuals


def test_manual_match_rejects_already_claimed_id(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    auto_match = state.run.auto_matches()[0]

    bank_id = state.run.unmatched_bank[0].external_id
    with pytest.raises(ManualMatchError):
        manual_match(tmp_path, state, auto_match.ledger_ids[0], bank_id)


def test_manual_match_rejects_double_claim(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    ledger_id = state.run.unmatched_ledger[0].external_id
    bank_id_a = state.run.unmatched_bank[0].external_id
    bank_id_b = state.run.unmatched_bank[1].external_id

    manual_match(tmp_path, state, ledger_id, bank_id_a)
    with pytest.raises(ManualMatchError):
        manual_match(tmp_path, state, ledger_id, bank_id_b)


def test_decisions_persist_across_session_reload(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    target = state.run.review_matches()[0]
    accept(tmp_path, state, target)
    ledger_id = state.run.unmatched_ledger[0].external_id
    bank_id = state.run.unmatched_bank[0].external_id
    manual_match(tmp_path, state, ledger_id, bank_id)

    reloaded = load_session(tmp_path, ledger, bank)
    reloaded_target = next(
        m for m in reloaded.run.review_matches() if match_key(m) == match_key(target)
    )
    assert reloaded.decision_for(reloaded_target) == Decision.ACCEPTED
    assert any(
        m.ledger_ids == [ledger_id] and m.bank_ids == [bank_id] for m in reloaded.manual_matches
    )


def test_audit_log_records_manual_decisions_without_amounts(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = load_session(tmp_path, ledger, bank)
    target = state.run.review_matches()[0]
    accept(tmp_path, state, target)
    reject(tmp_path, state, state.run.review_matches()[1])

    log_path = tmp_path / "audit_log.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    actions = {json.loads(line)["action"] for line in lines}
    assert actions == {"manual_match", "manual_reject_suggestion"}
    for line in lines:
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
        assert entry["actor"] == "user"


def test_save_session_is_pure_review_state_file_only(tmp_path: Path) -> None:
    ledger, bank = _load_sample()
    state = ReviewState(run=load_session(tmp_path, ledger, bank).run)
    save_session(tmp_path, state)
    assert (tmp_path / "review_state.json").exists()
