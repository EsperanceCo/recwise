"""TUI screens: dashboard, review (accept/reject/manual match), statement.

No business logic here either -- every action calls straight into
recwise.review / recwise.reconciliation / recwise.export, same as the
web app's routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from recwise import review
from recwise.export import export_reconciliation
from recwise.matching.models import Match
from recwise.reconciliation import build_statement

if TYPE_CHECKING:
    from recwise.tui.app import RecwiseApp


class DashboardScreen(Screen[None]):
    BINDINGS = [
        Binding("v", "goto_review", "Review"),
        Binding("s", "goto_statement", "Statement"),
        Binding("e", "do_export", "Export"),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_summary()

    def refresh_summary(self) -> None:
        app = cast("RecwiseApp", self.app)
        ledger, bank, state = app.session.load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)
        lines = [
            f"Ledger rows: {len(ledger)}   Bank rows: {len(bank)}",
            f"Auto-matched: {len(snapshot.auto_matches())}   "
            f"Needs review: {len(state.pending_matches())}",
            "",
            f"Balance per bank:   {statement.balance_per_bank}",
            f"Balance per ledger: {statement.balance_per_ledger}",
            f"Reconciled balance: {statement.reconciled_balance}",
            "",
            f"Suggested journals: {len(statement.suggested_journals)}",
            "",
            "[v] review   [s] statement   [e] export   [q] quit",
        ]
        self.query_one("#summary", Static).update("\n".join(lines))

    def action_goto_review(self) -> None:
        self.app.push_screen(ReviewScreen())

    def action_goto_statement(self) -> None:
        self.app.push_screen(StatementScreen())

    def action_do_export(self) -> None:
        app = cast("RecwiseApp", self.app)
        ledger, bank, state = app.session.load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)
        export_reconciliation(app.session.out_dir, statement, snapshot.matches)
        self.refresh_summary()


class ReviewScreen(Screen[None]):
    BINDINGS = [
        Binding("a", "accept_selected", "Accept"),
        Binding("r", "reject_selected", "Reject"),
        Binding("m", "goto_manual_match", "Manual match"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pending: list[Match] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="pending-table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_table()

    def refresh_table(self) -> None:
        app = cast("RecwiseApp", self.app)
        ledger, bank, state = app.session.load()
        ledger_by_id = {t.external_id: t for t in ledger}
        bank_by_id = {t.external_id: t for t in bank}
        self._pending = state.pending_matches()

        table = self.query_one("#pending-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Tier", "Confidence", "Ledger side", "Bank side", "Reason")
        for m in self._pending:
            ledger_side = "; ".join(f"{i} ({ledger_by_id[i].amount})" for i in m.ledger_ids)
            bank_side = "; ".join(f"{i} ({bank_by_id[i].amount})" for i in m.bank_ids)
            table.add_row(m.tier.value, f"{m.confidence:.2f}", ledger_side, bank_side, m.reason)
        self.query_one("#status", Static).update(f"{len(self._pending)} pending review")

    def _selected_match(self) -> Match | None:
        table = self.query_one("#pending-table", DataTable)
        if not self._pending or table.cursor_row is None:
            return None
        if table.cursor_row >= len(self._pending):
            return None
        return self._pending[table.cursor_row]

    def action_accept_selected(self) -> None:
        target = self._selected_match()
        if target is None:
            return
        app = cast("RecwiseApp", self.app)
        _, _, state = app.session.load()
        review.accept(app.session.out_dir, state, target)
        self.refresh_table()

    def action_reject_selected(self) -> None:
        target = self._selected_match()
        if target is None:
            return
        app = cast("RecwiseApp", self.app)
        _, _, state = app.session.load()
        review.reject(app.session.out_dir, state, target)
        self.refresh_table()

    def action_goto_manual_match(self) -> None:
        self.app.push_screen(ManualMatchScreen())


class ManualMatchScreen(Screen[None]):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("Enter the exact ledger and bank transaction ids to match:"),
            Horizontal(
                Input(placeholder="ledger id, e.g. LGR-000123", id="ledger-id"),
                Input(placeholder="bank id, e.g. BNK-000456", id="bank-id"),
            ),
            Button("Match these", id="submit-match"),
            Static("", id="manual-status"),
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "submit-match":
            return
        ledger_id = self.query_one("#ledger-id", Input).value.strip()
        bank_id = self.query_one("#bank-id", Input).value.strip()
        status = self.query_one("#manual-status", Static)
        if not ledger_id or not bank_id:
            status.update("Enter both a ledger id and a bank id.")
            return

        app = cast("RecwiseApp", self.app)
        _, _, state = app.session.load()
        try:
            review.manual_match(app.session.out_dir, state, ledger_id, bank_id)
        except review.ManualMatchError as exc:
            status.update(f"Error: {exc}")
            return
        status.update(f"Matched {ledger_id} <-> {bank_id}.")
        self.query_one("#ledger-id", Input).value = ""
        self.query_one("#bank-id", Input).value = ""


class StatementScreen(Screen[None]):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="statement-table")
        yield Footer()

    def on_mount(self) -> None:
        app = cast("RecwiseApp", self.app)
        ledger, bank, state = app.session.load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)

        table = self.query_one("#statement-table", DataTable)
        table.add_columns("Kind", "ID(s)", "Amount", "Note")
        for item in statement.ledger_only_items:
            table.add_row("ledger-only", item.external_id, str(item.amount), item.description)
        for item in statement.bank_only_items:
            table.add_row("bank-only", item.external_id, str(item.amount), item.description)
        for d in statement.discrepancy_items:
            table.add_row(
                "discrepancy",
                f"{d.ledger_id} / {d.bank_id}",
                str(d.residual),
                d.reason,
            )
        for note in statement.pending_review_notes:
            ids = ",".join(note.ledger_ids + note.bank_ids)
            table.add_row("pending", ids, "-", note.reason)
