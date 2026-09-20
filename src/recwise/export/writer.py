"""Write a reconciliation run to CSV files for a human to review.

Every text cell goes through sanitize_cell() -- descriptions, ids, and
narratives can all carry untrusted text that originated in the input
files, so sanitizing uniformly (rather than reasoning field-by-field
about what's "safe") is the conservative, correct choice. Numeric cells
(amounts, confidence scores) are written as-is: negative numbers stay
numeric per CLAUDE.md, never text-prefixed.

Read-only with respect to the user's original input files -- this module
only ever creates new files in the given output directory.
"""

from __future__ import annotations

import csv
from pathlib import Path

from recwise.export.sanitize import sanitize_cell
from recwise.matching.models import Match
from recwise.reconciliation.models import ReconciliationStatement

MATCHES_FILENAME = "matches.csv"
LEDGER_ONLY_FILENAME = "ledger_only_items.csv"
BANK_ONLY_FILENAME = "bank_only_items.csv"
DISCREPANCIES_FILENAME = "discrepancies.csv"
PENDING_REVIEW_FILENAME = "pending_review.csv"
SUGGESTED_JOURNALS_FILENAME = "suggested_journals.csv"
SUMMARY_FILENAME = "reconciliation_summary.csv"


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def write_matches_csv(path: Path, matches: list[Match]) -> None:
    rows = [
        [
            sanitize_cell(m.tier.value),
            sanitize_cell(m.status.value),
            sanitize_cell(";".join(m.ledger_ids)),
            sanitize_cell(";".join(m.bank_ids)),
            str(m.confidence),
            sanitize_cell(m.reason),
        ]
        for m in matches
    ]
    _write_csv(path, ["tier", "status", "ledger_ids", "bank_ids", "confidence", "reason"], rows)


def _write_reconciling_items(path: Path, statement: ReconciliationStatement, source: str) -> None:
    items = statement.ledger_only_items if source == "ledger" else statement.bank_only_items
    rows = [
        [
            sanitize_cell(item.external_id),
            item.txn_date.isoformat(),
            str(item.amount),
            sanitize_cell(item.description),
        ]
        for item in items
    ]
    _write_csv(path, ["external_id", "date", "amount", "description"], rows)


def write_discrepancies_csv(path: Path, statement: ReconciliationStatement) -> None:
    rows = [
        [
            sanitize_cell(item.ledger_id),
            sanitize_cell(item.bank_id),
            str(item.ledger_amount),
            str(item.bank_amount),
            str(item.residual),
            sanitize_cell(item.ledger_description),
            sanitize_cell(item.bank_description),
            sanitize_cell(item.reason),
        ]
        for item in statement.discrepancy_items
    ]
    _write_csv(
        path,
        [
            "ledger_id",
            "bank_id",
            "ledger_amount",
            "bank_amount",
            "residual",
            "ledger_description",
            "bank_description",
            "reason",
        ],
        rows,
    )


def write_pending_review_csv(path: Path, statement: ReconciliationStatement) -> None:
    rows = [
        [
            sanitize_cell(note.tier),
            sanitize_cell(";".join(note.ledger_ids)),
            sanitize_cell(";".join(note.bank_ids)),
            sanitize_cell(note.reason),
        ]
        for note in statement.pending_review_notes
    ]
    _write_csv(path, ["tier", "ledger_ids", "bank_ids", "reason"], rows)


def write_suggested_journals_csv(path: Path, statement: ReconciliationStatement) -> None:
    rows = [
        [
            sanitize_cell(j.narrative),
            sanitize_cell(j.debit_account),
            sanitize_cell(j.credit_account),
            str(j.amount),
            sanitize_cell(j.source_bank_id),
        ]
        for j in statement.suggested_journals
    ]
    _write_csv(
        path, ["narrative", "debit_account", "credit_account", "amount", "source_bank_id"], rows
    )


def write_summary_csv(path: Path, statement: ReconciliationStatement) -> None:
    rows: list[list[str]] = [
        ["balance_per_bank", str(statement.balance_per_bank)],
        ["balance_per_ledger", str(statement.balance_per_ledger)],
        ["reconciled_balance", str(statement.reconciled_balance)],
        ["ledger_only_item_count", str(len(statement.ledger_only_items))],
        ["bank_only_item_count", str(len(statement.bank_only_items))],
        ["discrepancy_count", str(len(statement.discrepancy_items))],
        ["pending_review_count", str(len(statement.pending_review_notes))],
        ["suggested_journal_count", str(len(statement.suggested_journals))],
    ]
    _write_csv(path, ["field", "value"], rows)


def export_reconciliation(
    out_dir: Path,
    statement: ReconciliationStatement,
    matches: list[Match],
) -> None:
    """Write every export file into out_dir. Never touches input files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_matches_csv(out_dir / MATCHES_FILENAME, matches)
    _write_reconciling_items(out_dir / LEDGER_ONLY_FILENAME, statement, "ledger")
    _write_reconciling_items(out_dir / BANK_ONLY_FILENAME, statement, "bank")
    write_discrepancies_csv(out_dir / DISCREPANCIES_FILENAME, statement)
    write_pending_review_csv(out_dir / PENDING_REVIEW_FILENAME, statement)
    write_suggested_journals_csv(out_dir / SUGGESTED_JOURNALS_FILENAME, statement)
    write_summary_csv(out_dir / SUMMARY_FILENAME, statement)
