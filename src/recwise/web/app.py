"""Local review web app: accept/reject suggestions, manually match, export.

Bound to 127.0.0.1 only (see cli.py) per CLAUDE.md. Stateless per request
by design: every request reloads the ledger/bank files and re-runs
matching (deterministic, fast at this scale) plus the saved review
decisions, rather than holding state in process memory -- simpler, and
safe across restarts. Jinja2's autoescaping (Flask's default) handles the
HTML-injection risk from untrusted transaction descriptions; this is a
different concern from the CSV/Excel formula-injection sanitize_cell()
handles in the export module.

No business logic here -- every route just calls into recwise.review,
recwise.matching, and recwise.reconciliation.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from recwise import review
from recwise.analytics import analyze as analyze_benford
from recwise.export import export_reconciliation
from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping
from recwise.importer.loader import load_bank_statement, load_ledger
from recwise.importer.models import Transaction
from recwise.matching import MatchConfig
from recwise.matching.models import Match
from recwise.reconciliation import build_statement
from recwise.review.state import ReviewState, match_key


def create_app(
    *,
    ledger_path: Path,
    bank_path: Path,
    ledger_mapping: LedgerColumnMapping,
    bank_mapping: BankColumnMapping,
    out_dir: Path,
    match_config: MatchConfig | None = None,
) -> Flask:
    app = Flask(__name__)
    # Generated once per process, in memory only -- not a persisted secret,
    # just enough to stop a malicious page in another tab from blind-POSTing
    # to this local server (CSRF). No new dependency: stdlib secrets only.
    csrf_token = secrets.token_hex(32)

    def _load() -> tuple[list[Transaction], list[Transaction], ReviewState]:
        ledger = load_ledger(ledger_path, ledger_mapping)
        bank = load_bank_statement(bank_path, bank_mapping)
        state = review.load_session(out_dir, ledger, bank, match_config)
        return ledger, bank, state

    def _check_csrf() -> None:
        if request.form.get("csrf_token") != csrf_token:
            abort(400, "invalid or missing CSRF token")

    def _find_review_match(state: ReviewState, key: str) -> Match:
        target = next((m for m in state.run.review_matches() if match_key(m) == key), None)
        if target is None:
            abort(404, "unknown or already-resolved suggestion")
        return target

    @app.context_processor
    def _inject_csrf() -> dict[str, str]:
        return {"csrf_token": csrf_token}

    @app.get("/")
    def index() -> str:
        ledger, bank, state = _load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)
        return render_template(
            "index.html",
            ledger_count=len(ledger),
            bank_count=len(bank),
            auto_count=len(snapshot.auto_matches()),
            pending_count=len(state.pending_matches()),
            statement=statement,
        )

    @app.get("/review")
    def review_list() -> str:
        ledger, bank, state = _load()
        ledger_by_id = {t.external_id: t for t in ledger}
        bank_by_id = {t.external_id: t for t in bank}

        rows = [
            {
                "key": match_key(m),
                "tier": m.tier.value,
                "confidence": m.confidence,
                "reason": m.reason,
                "ledger_txns": [ledger_by_id[i] for i in m.ledger_ids],
                "bank_txns": [bank_by_id[i] for i in m.bank_ids],
            }
            for m in state.pending_matches()
        ]
        available_ledger = sorted(
            (ledger_by_id[i] for i in state.available_ledger_ids()), key=lambda t: t.external_id
        )
        available_bank = sorted(
            (bank_by_id[i] for i in state.available_bank_ids()), key=lambda t: t.external_id
        )
        return render_template(
            "review.html",
            rows=rows,
            available_ledger=available_ledger,
            available_bank=available_bank,
        )

    @app.post("/review/accept")
    def accept_route() -> Response:
        _check_csrf()
        _, _, state = _load()
        target = _find_review_match(state, request.form["key"])
        review.accept(out_dir, state, target)
        return redirect(url_for("review_list"))

    @app.post("/review/reject")
    def reject_route() -> Response:
        _check_csrf()
        _, _, state = _load()
        target = _find_review_match(state, request.form["key"])
        review.reject(out_dir, state, target)
        return redirect(url_for("review_list"))

    @app.post("/review/manual-match")
    def manual_match_route() -> Response:
        _check_csrf()
        _, _, state = _load()
        try:
            review.manual_match(out_dir, state, request.form["ledger_id"], request.form["bank_id"])
        except review.ManualMatchError as exc:
            abort(400, str(exc))
        return redirect(url_for("review_list"))

    @app.get("/analytics")
    def analytics_view() -> str:
        ledger, bank, _ = _load()
        return render_template(
            "analytics.html",
            ledger_result=analyze_benford(ledger),
            bank_result=analyze_benford(bank),
        )

    @app.get("/statement")
    def statement_view() -> str:
        ledger, bank, state = _load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)
        return render_template("statement.html", statement=statement)

    @app.post("/export")
    def export_route() -> Response:
        _check_csrf()
        ledger, bank, state = _load()
        snapshot = state.to_match_run(ledger, bank)
        statement = build_statement(ledger, bank, snapshot)
        export_reconciliation(out_dir, statement, snapshot.matches)
        return redirect(url_for("index"))

    return app
