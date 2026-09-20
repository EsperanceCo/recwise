"""Save/load review decisions so a session survives closing the browser or
restarting the TUI. Stores only ids and decisions -- no descriptions,
amounts, or account numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

from recwise.matching.models import Match, MatchRun, MatchStatus, MatchTier
from recwise.review.state import MANUAL_MATCH_REASON, Decision, ReviewState

REVIEW_STATE_FILENAME = "review_state.json"


def save(path: Path, state: ReviewState) -> None:
    payload = {
        "decisions": {key: decision.value for key, decision in state.decisions.items()},
        "manual_matches": [
            {"ledger_ids": m.ledger_ids, "bank_ids": m.bank_ids} for m in state.manual_matches
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load(path: Path, run: MatchRun) -> ReviewState:
    """Load decisions against a freshly computed MatchRun. Matching is
    deterministic, so a decision keyed by match content reattaches to the
    same suggestion on the next run against the same input files."""
    path = Path(path)
    if not path.exists():
        return ReviewState(run=run)

    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = {key: Decision(value) for key, value in payload.get("decisions", {}).items()}
    manual_matches = [
        Match(
            tier=MatchTier.MANUAL,
            status=MatchStatus.AUTO,
            ledger_ids=entry["ledger_ids"],
            bank_ids=entry["bank_ids"],
            confidence=1.0,
            reason=MANUAL_MATCH_REASON,
        )
        for entry in payload.get("manual_matches", [])
    ]
    return ReviewState(run=run, decisions=decisions, manual_matches=manual_matches)
