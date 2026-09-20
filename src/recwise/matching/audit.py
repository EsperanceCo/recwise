"""Append-only audit log: every match, unmatch, and manual decision.

Per CLAUDE.md's matching-integrity rules. Entries are appended as JSON
Lines so the log is never rewritten, only ever grown. Log entries carry
only ids, tiers, confidence, and timing -- never transaction descriptions,
amounts, or account numbers. Deliberately does NOT store Match.reason:
those plain-English reasons interpolate amounts and account refs (by
design, for the human-facing matches.csv export), so they must never
flow into this log. The tier alone is the safe stand-in for "why."
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from recwise.matching.models import Match, MatchRun, MatchStatus, MatchTier

AUDIT_LOG_FILENAME = "audit_log.jsonl"


class AuditAction(StrEnum):
    AUTO_MATCH = "auto_match"
    REVIEW_SUGGESTED = "review_suggested"
    MANUAL_MATCH = "manual_match"
    MANUAL_UNMATCH = "manual_unmatch"
    MANUAL_REJECT_SUGGESTION = "manual_reject_suggestion"


@dataclass(frozen=True)
class AuditLogEntry:
    timestamp: str
    action: AuditAction
    tier: MatchTier | None
    ledger_ids: list[str]
    bank_ids: list[str]
    confidence: float | None
    actor: str = "system"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def entries_from_match_run(run: MatchRun, *, timestamp: str | None = None) -> list[AuditLogEntry]:
    """Build one audit entry per match produced by an engine run.

    Note: only ids, tier, and confidence are logged -- never descriptions,
    amounts, or account numbers, and never Match.reason (see module docstring).
    """
    ts = timestamp if timestamp is not None else _now()
    entries: list[AuditLogEntry] = []
    for match in run.matches:
        action = (
            AuditAction.AUTO_MATCH
            if match.status == MatchStatus.AUTO
            else AuditAction.REVIEW_SUGGESTED
        )
        entries.append(
            AuditLogEntry(
                timestamp=ts,
                action=action,
                tier=match.tier,
                ledger_ids=match.ledger_ids,
                bank_ids=match.bank_ids,
                confidence=match.confidence,
                actor="system",
            )
        )
    return entries


def entry_for_manual_decision(
    action: AuditAction, m: Match, *, actor: str = "user", timestamp: str | None = None
) -> AuditLogEntry:
    """Build a single audit entry for a manual accept/reject/manual-match
    decision. Used by the review layer -- never carries m.reason."""
    return AuditLogEntry(
        timestamp=timestamp if timestamp is not None else _now(),
        action=action,
        tier=m.tier,
        ledger_ids=m.ledger_ids,
        bank_ids=m.bank_ids,
        confidence=m.confidence,
        actor=actor,
    )


def _entry_to_json_dict(entry: AuditLogEntry) -> dict[str, object]:
    payload = asdict(entry)
    payload["action"] = entry.action.value
    payload["tier"] = entry.tier.value if entry.tier is not None else None
    return payload


def append_entries(path: Path, entries: list[AuditLogEntry]) -> None:
    """Append entries to the audit log, one JSON object per line."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(_entry_to_json_dict(entry), ensure_ascii=False))
            fh.write("\n")


def read_entries(path: Path) -> list[dict[str, object]]:
    """Read back the audit log as plain dicts (for tests and inspection)."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
