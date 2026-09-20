"""Data models for the matching engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from recwise.importer.models import Transaction


class MatchTier(StrEnum):
    """Which rule produced a match, in the plain-English reason every match carries."""

    EXACT = "exact"
    DATE_WINDOW = "date_window"
    ONE_TO_MANY = "one_to_many"
    FUZZY_DISCREPANCY = "fuzzy_discrepancy"


class MatchStatus(StrEnum):
    """AUTO = confirmed automatically. REVIEW = a suggestion; a human decides."""

    AUTO = "auto"
    REVIEW = "review"


@dataclass(frozen=True)
class Match:
    """One proposed or confirmed match, one-to-one or one-to-many.

    `ledger_ids` / `bank_ids` are external_id values from Transaction. More
    than one id on a side means either a one-to-many grouping or an
    ambiguous set of candidates awaiting a human decision (never both
    sides having more than one id unless the ambiguity spans several
    same-amount rows on both sides).
    """

    tier: MatchTier
    status: MatchStatus
    ledger_ids: list[str]
    bank_ids: list[str]
    confidence: float
    reason: str


@dataclass
class MatchRun:
    """The full output of one matching pass."""

    matches: list[Match] = field(default_factory=list)
    unmatched_ledger: list[Transaction] = field(default_factory=list)
    unmatched_bank: list[Transaction] = field(default_factory=list)

    def auto_matches(self) -> list[Match]:
        return [m for m in self.matches if m.status == MatchStatus.AUTO]

    def review_matches(self) -> list[Match]:
        return [m for m in self.matches if m.status == MatchStatus.REVIEW]
