"""Terminal review UI: same actions as the web app (accept/reject/manual
match/export), same recwise.review service layer underneath, just a
different front end.
"""

from __future__ import annotations

from textual.app import App

from recwise.tui.screens import DashboardScreen
from recwise.tui.session import SessionConfig


class RecwiseApp(App[None]):
    TITLE = "Recwise"

    def __init__(self, session: SessionConfig) -> None:
        super().__init__()
        self.session = session

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())
