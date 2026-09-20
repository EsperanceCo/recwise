"""Persisted web-session configuration: which files and column mapping to
use, chosen once via the browser /setup flow instead of CLI flags. This is
what lets the packaged desktop app launch with no arguments and ask the
user in-browser, while `recwise-review --ledger ... --bank ...` keeps
working exactly as before (those flags bypass this file entirely).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from recwise.importer.column_mapping import BankColumnMapping, LedgerColumnMapping

SESSION_CONFIG_FILENAME = "session_config.json"


class SessionNotConfigured(Exception):
    """No ledger/bank files and column mapping have been chosen yet."""


@dataclass(frozen=True)
class SessionConfig:
    ledger_path: Path
    bank_path: Path
    ledger_mapping: LedgerColumnMapping
    bank_mapping: BankColumnMapping


def save_session_config(out_dir: Path, config: SessionConfig) -> None:
    payload = {
        "ledger_path": str(config.ledger_path),
        "bank_path": str(config.bank_path),
        "ledger_mapping": asdict(config.ledger_mapping),
        "bank_mapping": asdict(config.bank_mapping),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = out_dir / SESSION_CONFIG_FILENAME
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session_config(out_dir: Path) -> SessionConfig:
    config_path = out_dir / SESSION_CONFIG_FILENAME
    if not config_path.is_file():
        raise SessionNotConfigured(f"no session configured yet: {config_path} does not exist")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        return SessionConfig(
            ledger_path=Path(payload["ledger_path"]),
            bank_path=Path(payload["bank_path"]),
            ledger_mapping=LedgerColumnMapping(**payload["ledger_mapping"]),
            bank_mapping=BankColumnMapping(**payload["bank_mapping"]),
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SessionNotConfigured(f"session config at {config_path} is invalid: {exc}") from exc
