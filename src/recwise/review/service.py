"""Orchestration for the review layer: load a session, apply a decision,
persist it, and audit-log it. This is the one thing both the web app and
the TUI call -- neither carries this wiring itself.
"""

from __future__ import annotations

from pathlib import Path

from recwise.importer.models import Transaction
from recwise.matching import MatchConfig, match
from recwise.matching.audit import (
    AUDIT_LOG_FILENAME,
    AuditAction,
    append_entries,
    entry_for_manual_decision,
)
from recwise.matching.models import Match
from recwise.review import persistence
from recwise.review.state import ManualMatchError, ReviewState

__all__ = ["ManualMatchError", "accept", "load_session", "manual_match", "reject", "save_session"]


def load_session(
    out_dir: Path,
    ledger: list[Transaction],
    bank: list[Transaction],
    config: MatchConfig | None = None,
) -> ReviewState:
    """Re-run matching (deterministic) and reattach any saved decisions."""
    run = match(ledger, bank, config)
    return persistence.load(Path(out_dir) / persistence.REVIEW_STATE_FILENAME, run)


def save_session(out_dir: Path, state: ReviewState) -> None:
    persistence.save(Path(out_dir) / persistence.REVIEW_STATE_FILENAME, state)


def _audit(out_dir: Path, action: AuditAction, m: Match) -> None:
    append_entries(Path(out_dir) / AUDIT_LOG_FILENAME, [entry_for_manual_decision(action, m)])


def accept(out_dir: Path, state: ReviewState, m: Match) -> None:
    state.accept(m)
    save_session(out_dir, state)
    _audit(out_dir, AuditAction.MANUAL_MATCH, m)


def reject(out_dir: Path, state: ReviewState, m: Match) -> None:
    state.reject(m)
    save_session(out_dir, state)
    _audit(out_dir, AuditAction.MANUAL_REJECT_SUGGESTION, m)


def manual_match(out_dir: Path, state: ReviewState, ledger_id: str, bank_id: str) -> Match:
    new_match = state.manual_match(ledger_id, bank_id)
    save_session(out_dir, state)
    _audit(out_dir, AuditAction.MANUAL_MATCH, new_match)
    return new_match
