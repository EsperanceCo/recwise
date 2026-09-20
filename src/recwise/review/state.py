"""Review decision state: accept/reject a suggestion, or manually pair two
transactions. Pure logic, no I/O -- consumed identically by the web app and
the TUI so neither carries its own copy of these rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from recwise.importer.models import Transaction
from recwise.matching.models import Match, MatchRun, MatchStatus, MatchTier

MANUAL_MATCH_REASON = "manually matched by user"


class Decision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ManualMatchError(ValueError):
    """Raised when a manual match request targets an id that isn't
    actually available (already settled, or unknown)."""


def match_key(m: Match) -> str:
    """Stable, content-derived identity for a Match -- independent of list
    order or object identity, so decisions survive a fresh match() run on
    the same input (matching is deterministic, so the same suggestion
    reappears with the same key)."""
    ledger_part = "|".join(sorted(m.ledger_ids))
    bank_part = "|".join(sorted(m.bank_ids))
    return f"{m.tier.value}:{ledger_part}:{bank_part}"


@dataclass
class ReviewState:
    run: MatchRun
    decisions: dict[str, Decision] = field(default_factory=dict)
    manual_matches: list[Match] = field(default_factory=list)

    def decision_for(self, m: Match) -> Decision:
        return self.decisions.get(match_key(m), Decision.PENDING)

    def pending_matches(self) -> list[Match]:
        return [m for m in self.run.review_matches() if self.decision_for(m) == Decision.PENDING]

    def accept(self, m: Match) -> None:
        self.decisions[match_key(m)] = Decision.ACCEPTED

    def reject(self, m: Match) -> None:
        self.decisions[match_key(m)] = Decision.REJECTED

    def _manually_claimed_ids(self) -> tuple[set[str], set[str]]:
        ledger_ids = {lid for m in self.manual_matches for lid in m.ledger_ids}
        bank_ids = {bid for m in self.manual_matches for bid in m.bank_ids}
        return ledger_ids, bank_ids

    def available_ledger_ids(self) -> set[str]:
        """ids a human could still pick for a manual match: unmatched by
        the engine, or part of a still-pending/rejected suggestion, and
        not already claimed by an earlier manual match."""
        manually_claimed, _ = self._manually_claimed_ids()
        ids = {t.external_id for t in self.run.unmatched_ledger}
        for m in self.run.review_matches():
            if self.decision_for(m) != Decision.ACCEPTED:
                ids.update(m.ledger_ids)
        return ids - manually_claimed

    def available_bank_ids(self) -> set[str]:
        _, manually_claimed = self._manually_claimed_ids()
        ids = {t.external_id for t in self.run.unmatched_bank}
        for m in self.run.review_matches():
            if self.decision_for(m) != Decision.ACCEPTED:
                ids.update(m.bank_ids)
        return ids - manually_claimed

    def manual_match(self, ledger_id: str, bank_id: str) -> Match:
        if ledger_id not in self.available_ledger_ids():
            raise ManualMatchError(f"ledger id {ledger_id!r} is not available for manual matching")
        if bank_id not in self.available_bank_ids():
            raise ManualMatchError(f"bank id {bank_id!r} is not available for manual matching")
        new_match = Match(
            tier=MatchTier.MANUAL,
            status=MatchStatus.AUTO,
            ledger_ids=[ledger_id],
            bank_ids=[bank_id],
            confidence=1.0,
            reason=MANUAL_MATCH_REASON,
        )
        self.manual_matches.append(new_match)
        return new_match

    def to_match_run(self, ledger: list[Transaction], bank: list[Transaction]) -> MatchRun:
        """The current confirmed snapshot: auto matches, accepted review
        matches, and manual matches. Everything else -- rejected, still
        pending, or genuinely unmatched -- is reported as unmatched, ready
        to feed straight into build_statement()."""
        confirmed: list[Match] = list(self.run.auto_matches())
        settled_ledger_ids: set[str] = set()
        settled_bank_ids: set[str] = set()
        for m in confirmed:
            settled_ledger_ids.update(m.ledger_ids)
            settled_bank_ids.update(m.bank_ids)

        for m in self.run.review_matches():
            if self.decision_for(m) == Decision.ACCEPTED:
                confirmed.append(m)
                settled_ledger_ids.update(m.ledger_ids)
                settled_bank_ids.update(m.bank_ids)

        for m in self.manual_matches:
            confirmed.append(m)
            settled_ledger_ids.update(m.ledger_ids)
            settled_bank_ids.update(m.bank_ids)

        unmatched_ledger = [t for t in ledger if t.external_id not in settled_ledger_ids]
        unmatched_bank = [t for t in bank if t.external_id not in settled_bank_ids]
        return MatchRun(
            matches=confirmed, unmatched_ledger=unmatched_ledger, unmatched_bank=unmatched_bank
        )
