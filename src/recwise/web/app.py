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

The /setup route (recwise.web.uploads, recwise.web.session_config) exists
so the packaged desktop app can launch with no CLI arguments: it lets a
user pick their ledger/bank files and column mapping in the browser
instead. `recwise-review --ledger/--bank` still bypasses it entirely.
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
from recwise.importer.errors import RecwiseImportError
from recwise.importer.loader import load_bank_statement, load_ledger
from recwise.importer.models import Transaction
from recwise.matching import MatchConfig
from recwise.matching.models import Match
from recwise.reconciliation import build_statement
from recwise.review.state import ReviewState, match_key
from recwise.web.session_config import (
    SessionConfig,
    SessionNotConfigured,
    load_session_config,
    save_session_config,
)
from recwise.web.uploads import UnsupportedUploadError, save_upload, upload_suffix

# Two uploaded files (ledger + bank) per /setup submission, each capped at
# the importer's own per-file limit -- Flask rejects an oversized request
# outright rather than buffering it first.
_MAX_UPLOAD_REQUEST_BYTES = 2 * 50 * 1024 * 1024


def create_app(
    *,
    out_dir: Path,
    ledger_path: Path | None = None,
    bank_path: Path | None = None,
    ledger_mapping: LedgerColumnMapping | None = None,
    bank_mapping: BankColumnMapping | None = None,
    match_config: MatchConfig | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = _MAX_UPLOAD_REQUEST_BYTES
    # Generated once per process, in memory only -- not a persisted secret,
    # just enough to stop a malicious page in another tab from blind-POSTing
    # to this local server (CSRF). No new dependency: stdlib secrets only.
    csrf_token = secrets.token_hex(32)

    def _resolve_session() -> tuple[Path, Path, LedgerColumnMapping, BankColumnMapping]:
        # CLI-supplied paths (recwise-review --ledger/--bank) always win, so
        # that invocation keeps behaving exactly as before /setup existed.
        if (
            ledger_path is not None
            and bank_path is not None
            and ledger_mapping is not None
            and bank_mapping is not None
        ):
            return ledger_path, bank_path, ledger_mapping, bank_mapping
        config = load_session_config(out_dir)  # raises SessionNotConfigured
        return config.ledger_path, config.bank_path, config.ledger_mapping, config.bank_mapping

    def _load() -> tuple[list[Transaction], list[Transaction], ReviewState]:
        l_path, b_path, l_mapping, b_mapping = _resolve_session()
        ledger = load_ledger(l_path, l_mapping)
        bank = load_bank_statement(b_path, b_mapping)
        state = review.load_session(out_dir, ledger, bank, match_config)
        return ledger, bank, state

    @app.before_request
    def _require_setup() -> Response | None:
        if request.endpoint in {"setup_view", "setup_submit", "static"}:
            return None
        try:
            _resolve_session()
        except SessionNotConfigured:
            return redirect(url_for("setup_view"))
        return None

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

    @app.get("/setup")
    def setup_view() -> str:
        return render_template("setup.html", error=None)

    @app.post("/setup")
    def setup_submit() -> Response | str:
        _check_csrf()
        ledger_file = request.files.get("ledger_file")
        bank_file = request.files.get("bank_file")
        if ledger_file is None or not ledger_file.filename:
            return render_template("setup.html", error="Choose a ledger file.")
        if bank_file is None or not bank_file.filename:
            return render_template("setup.html", error="Choose a bank statement file.")
        ledger_filename: str = ledger_file.filename
        bank_filename: str = bank_file.filename

        try:
            ledger_suffix = upload_suffix(ledger_filename)
            bank_suffix = upload_suffix(bank_filename)
            upload_dir = out_dir / "uploads"
            ledger_dest = save_upload(upload_dir, "ledger", ledger_suffix, ledger_file)
            bank_dest = save_upload(upload_dir, "bank", bank_suffix, bank_file)
        except UnsupportedUploadError as exc:
            return render_template("setup.html", error=str(exc))

        submitted_ledger_mapping = LedgerColumnMapping(
            date_col=request.form["ledger_date_col"],
            date_format=request.form["ledger_date_format"],
            description_col=request.form["ledger_description_col"],
            amount_col=request.form["ledger_amount_col"],
            account_col=request.form["ledger_account_col"],
            id_col=request.form.get("ledger_id_col") or None,
        )
        submitted_bank_mapping = BankColumnMapping(
            date_col=request.form["bank_date_col"],
            date_format=request.form["bank_date_format"],
            description_col=request.form["bank_description_col"],
            debit_col=request.form["bank_debit_col"],
            credit_col=request.form["bank_credit_col"],
            account_col=request.form["bank_account_col"],
            id_col=request.form.get("bank_id_col") or None,
        )

        try:
            load_ledger(ledger_dest, submitted_ledger_mapping)
            load_bank_statement(bank_dest, submitted_bank_mapping)
        except (RecwiseImportError, FileNotFoundError) as exc:
            return render_template("setup.html", error=f"Could not read the files: {exc}")

        save_session_config(
            out_dir,
            SessionConfig(
                ledger_path=ledger_dest,
                bank_path=bank_dest,
                ledger_mapping=submitted_ledger_mapping,
                bank_mapping=submitted_bank_mapping,
            ),
        )
        return redirect(url_for("index"))

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
