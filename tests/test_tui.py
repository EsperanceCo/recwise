import asyncio
import json
from pathlib import Path

from textual.widgets import Input

from recwise.importer.column_mapping import SAMPLE_BANK_MAPPING, SAMPLE_LEDGER_MAPPING
from recwise.tui.app import RecwiseApp
from recwise.tui.screens import DashboardScreen, ManualMatchScreen, ReviewScreen, StatementScreen
from recwise.tui.session import SessionConfig

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _session(out_dir: Path) -> SessionConfig:
    return SessionConfig(
        ledger_path=SAMPLE_DIR / "ledger.csv",
        bank_path=SAMPLE_DIR / "bank_statement.csv",
        ledger_mapping=SAMPLE_LEDGER_MAPPING,
        bank_mapping=SAMPLE_BANK_MAPPING,
        out_dir=out_dir,
    )


def test_app_mounts_dashboard(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(body())


def test_navigation_between_screens(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, StatementScreen)

    asyncio.run(body())


def test_accept_persists_decision(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ReviewScreen)
            target = screen._pending[0]
            await pilot.press("a")
            await pilot.pause()
            assert target not in screen._pending

    asyncio.run(body())

    payload = json.loads((tmp_path / "review_state.json").read_text(encoding="utf-8"))
    assert len(payload["decisions"]) == 1
    assert next(iter(payload["decisions"].values())) == "accepted"


def test_reject_returns_ids_to_unmatched(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()

    asyncio.run(body())

    payload = json.loads((tmp_path / "review_state.json").read_text(encoding="utf-8"))
    assert next(iter(payload["decisions"].values())) == "rejected"


def test_manual_match_screen_success(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ledger, bank, state = session.load()
    ledger_id = state.run.unmatched_ledger[0].external_id
    bank_id = state.run.unmatched_bank[0].external_id

    async def body() -> None:
        app = RecwiseApp(session)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ManualMatchScreen)
            screen.query_one("#ledger-id", Input).value = ledger_id
            screen.query_one("#bank-id", Input).value = bank_id
            await pilot.click("#submit-match")
            await pilot.pause()
            status = screen.query_one("#manual-status")
            assert "Matched" in str(status.render())

    asyncio.run(body())

    payload = json.loads((tmp_path / "review_state.json").read_text(encoding="utf-8"))
    assert payload["manual_matches"] == [{"ledger_ids": [ledger_id], "bank_ids": [bank_id]}]


def test_manual_match_screen_rejects_invalid_id(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ManualMatchScreen)
            screen.query_one("#ledger-id", Input).value = "not-a-real-id"
            screen.query_one("#bank-id", Input).value = "also-not-real"
            await pilot.click("#submit-match")
            await pilot.pause()
            status = screen.query_one("#manual-status")
            assert "Error" in str(status.render())

    asyncio.run(body())

    assert (
        not (tmp_path / "review_state.json").exists()
        or json.loads((tmp_path / "review_state.json").read_text(encoding="utf-8"))[
            "manual_matches"
        ]
        == []
    )


def test_export_writes_files(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()

    asyncio.run(body())

    assert (tmp_path / "matches.csv").exists()
    assert (tmp_path / "reconciliation_summary.csv").exists()


def test_audit_log_has_no_amounts(tmp_path: Path) -> None:
    async def body() -> None:
        app = RecwiseApp(_session(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()

    asyncio.run(body())

    lines = (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
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
