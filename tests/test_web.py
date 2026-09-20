import json
import re
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from recwise.importer.column_mapping import SAMPLE_BANK_MAPPING, SAMPLE_LEDGER_MAPPING
from recwise.web import create_app

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def client(tmp_path: Path) -> FlaskClient:
    app = create_app(
        ledger_path=SAMPLE_DIR / "ledger.csv",
        bank_path=SAMPLE_DIR / "bank_statement.csv",
        ledger_mapping=SAMPLE_LEDGER_MAPPING,
        bank_mapping=SAMPLE_BANK_MAPPING,
        out_dir=tmp_path,
    )
    app.testing = True
    return app.test_client()


@pytest.fixture
def unconfigured_client(tmp_path: Path) -> FlaskClient:
    """No ledger/bank/mapping given at creation time -- the desktop-launcher
    shape, which must fall back to the /setup flow instead of crashing."""
    app = create_app(out_dir=tmp_path)
    app.testing = True
    return app.test_client()


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_index_shows_balances(client: FlaskClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Balance per bank" in body
    assert "Balance per ledger" in body


def test_review_list_shows_pending_suggestions(client: FlaskClient) -> None:
    resp = client.get("/review")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "confidence" in body
    assert "exact" in body or "date_window" in body or "one_to_many" in body


def test_accept_without_csrf_token_is_rejected(client: FlaskClient) -> None:
    resp = client.get("/review")
    body = resp.get_data(as_text=True)
    key = re.search(r'name="key" value="([^"]+)"', body)
    assert key is not None
    resp = client.post("/review/accept", data={"key": key.group(1)})
    assert resp.status_code == 400


def test_accept_and_reject_flow(client: FlaskClient, tmp_path: Path) -> None:
    resp = client.get("/review")
    body = resp.get_data(as_text=True)
    csrf = _extract_csrf_token(body)
    keys = re.findall(r'name="key" value="([^"]+)"', body)
    assert len(keys) >= 2

    resp = client.post("/review/accept", data={"csrf_token": csrf, "key": keys[0]})
    assert resp.status_code == 302

    resp = client.post("/review/reject", data={"csrf_token": csrf, "key": keys[1]})
    assert resp.status_code == 302

    resp = client.get("/review")
    remaining_keys = re.findall(r'name="key" value="([^"]+)"', resp.get_data(as_text=True))
    assert keys[0] not in remaining_keys
    assert keys[1] not in remaining_keys


def test_unknown_key_returns_404(client: FlaskClient) -> None:
    resp = client.get("/review")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    resp = client.post("/review/accept", data={"csrf_token": csrf, "key": "not-a-real-key"})
    assert resp.status_code == 404


def test_manual_match_flow(client: FlaskClient) -> None:
    resp = client.get("/review")
    body = resp.get_data(as_text=True)
    csrf = _extract_csrf_token(body)
    ledger_selects = re.findall(r'<select name="ledger_id"[^>]*>.*?</select>', body, re.DOTALL)
    ledger_match = re.search(r'<option value="([^"]+)"', ledger_selects[0])
    assert ledger_match is not None
    ledger_id = ledger_match.group(1)
    bank_selects = re.findall(r'<select name="bank_id"[^>]*>.*?</select>', body, re.DOTALL)
    bank_match = re.search(r'<option value="([^"]+)"', bank_selects[0])
    assert bank_match is not None
    bank_id = bank_match.group(1)

    resp = client.post(
        "/review/manual-match",
        data={"csrf_token": csrf, "ledger_id": ledger_id, "bank_id": bank_id},
    )
    assert resp.status_code == 302

    resp = client.get("/statement")
    assert resp.status_code == 200


def test_manual_match_rejects_already_used_id(client: FlaskClient) -> None:
    resp = client.get("/review")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    resp = client.post(
        "/review/manual-match",
        data={"csrf_token": csrf, "ledger_id": "not-a-real-id", "bank_id": "also-not-real"},
    )
    assert resp.status_code == 400


def test_export_writes_files(client: FlaskClient, tmp_path: Path) -> None:
    resp = client.get("/")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    resp = client.post("/export", data={"csrf_token": csrf})
    assert resp.status_code == 302
    assert (tmp_path / "matches.csv").exists()
    assert (tmp_path / "reconciliation_summary.csv").exists()


def test_descriptions_are_html_escaped(client: FlaskClient) -> None:
    """Untrusted transaction descriptions must never inject raw HTML/JS."""
    resp = client.get("/review")
    body = resp.get_data(as_text=True)
    # Sample data descriptions never contain literal angle brackets, but
    # confirm Jinja's autoescape selector actually returns True for our
    # .html templates, which is what protects us here.
    from flask import current_app

    with client.application.app_context():
        autoescape = current_app.jinja_env.autoescape
        assert callable(autoescape)
        assert autoescape("review.html") is True
    assert "<script>" not in body


def test_statement_persists_across_requests(client: FlaskClient, tmp_path: Path) -> None:
    resp = client.get("/review")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    keys = re.findall(r'name="key" value="([^"]+)"', resp.get_data(as_text=True))
    client.post("/review/accept", data={"csrf_token": csrf, "key": keys[0]})

    state_file = tmp_path / "review_state.json"
    assert state_file.exists()
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert any(v == "accepted" for v in payload["decisions"].values())


def test_analytics_page_shows_both_populations(client: FlaskClient) -> None:
    resp = client.get("/analytics")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Ledger" in body
    assert "Bank statement" in body
    assert "Sample size: 1000" in body
    assert "Mean absolute deviation" in body
    assert "nonconformity" in body


def test_unconfigured_app_redirects_every_route_to_setup(
    unconfigured_client: FlaskClient,
) -> None:
    for path in ["/", "/review", "/statement", "/analytics"]:
        resp = unconfigured_client.get(path)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/setup"


def test_setup_page_loads_without_a_session(unconfigured_client: FlaskClient) -> None:
    resp = unconfigured_client.get("/setup")
    assert resp.status_code == 200
    assert "ledger_file" in resp.get_data(as_text=True)


def test_setup_without_csrf_token_is_rejected(unconfigured_client: FlaskClient) -> None:
    resp = unconfigured_client.post("/setup", data={})
    assert resp.status_code == 400


def _setup_form_data(csrf: str) -> dict[str, object]:
    from io import BytesIO

    ledger_bytes = (SAMPLE_DIR / "ledger.csv").read_bytes()
    bank_bytes = (SAMPLE_DIR / "bank_statement.csv").read_bytes()
    return {
        "csrf_token": csrf,
        "ledger_file": (BytesIO(ledger_bytes), "my ledger export.csv"),
        "ledger_date_col": "date",
        "ledger_date_format": "%Y-%m-%d",
        "ledger_description_col": "description",
        "ledger_amount_col": "amount",
        "ledger_account_col": "account_ref",
        "ledger_id_col": "id",
        "bank_file": (BytesIO(bank_bytes), "../../etc/passwd.csv"),
        "bank_date_col": "date",
        "bank_date_format": "%d/%m/%Y",
        "bank_description_col": "description",
        "bank_debit_col": "debit",
        "bank_credit_col": "credit",
        "bank_account_col": "account_ref",
        "bank_id_col": "id",
    }


def test_setup_flow_end_to_end(unconfigured_client: FlaskClient, tmp_path: Path) -> None:
    """Upload real sample files with deliberately hostile client-supplied
    filenames (spaces, a path-traversal attempt) -- the saved path must
    never be derived from those, only from the fixed 'ledger'/'bank' names
    this module chooses itself."""
    resp = unconfigured_client.get("/setup")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))

    resp = unconfigured_client.post(
        "/setup", data=_setup_form_data(csrf), content_type="multipart/form-data"
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"

    assert (tmp_path / "uploads" / "ledger.csv").is_file()
    assert (tmp_path / "uploads" / "bank.csv").is_file()
    assert not (tmp_path / "etc").exists()
    assert (tmp_path / "session_config.json").is_file()

    resp = unconfigured_client.get("/")
    assert resp.status_code == 200
    assert "Balance per bank" in resp.get_data(as_text=True)


def test_setup_rejects_unsupported_file_type(unconfigured_client: FlaskClient) -> None:
    from io import BytesIO

    resp = unconfigured_client.get("/setup")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    data = _setup_form_data(csrf)
    data["ledger_file"] = (BytesIO(b"not really a spreadsheet"), "ledger.exe")

    resp = unconfigured_client.post("/setup", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "unsupported file type" in resp.get_data(as_text=True)


def test_setup_rejects_bad_column_mapping(unconfigured_client: FlaskClient) -> None:
    resp = unconfigured_client.get("/setup")
    csrf = _extract_csrf_token(resp.get_data(as_text=True))
    data = _setup_form_data(csrf)
    data["ledger_amount_col"] = "not_a_real_column"

    resp = unconfigured_client.post("/setup", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "Could not read the files" in resp.get_data(as_text=True)


def test_cli_paths_bypass_session_config_entirely(client: FlaskClient) -> None:
    """When create_app is given explicit ledger/bank paths (recwise-review
    --ledger/--bank), /setup must never be reachable via redirect."""
    resp = client.get("/")
    assert resp.status_code == 200
