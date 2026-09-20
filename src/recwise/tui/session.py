"""Shared session context for the TUI: same load-fresh-every-time pattern
as the web app's `_load()` closure, for the same reasons (simplicity,
correctness, no risk of stale in-memory state across actions).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recwise import review
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.importer.loader import load_bank_statement, load_ledger
from recwise.importer.models import Transaction
from recwise.matching import MatchConfig
from recwise.review.state import ReviewState


@dataclass(frozen=True)
class SessionConfig:
    ledger_path: Path
    bank_path: Path
    ledger_mapping: LedgerColumnMapping
    bank_mapping: BankColumnMapping
    out_dir: Path
    match_config: MatchConfig | None = None

    def load(self) -> tuple[list[Transaction], list[Transaction], ReviewState]:
        ledger = load_ledger(self.ledger_path, self.ledger_mapping)
        bank = load_bank_statement(self.bank_path, self.bank_mapping)
        state = review.load_session(self.out_dir, ledger, bank, self.match_config)
        return ledger, bank, state
