"""Desktop-app launcher.

Entry point for the packaged Windows/macOS/Debian installer (see
pyproject.toml's [tool.briefcase] config) and for `python -m recwise` /
`recwise-app` from a terminal. Unlike `recwise-review`, this takes no
arguments: it starts the review server against a fixed per-user data
directory and lets the /setup page (recwise.web.app) ask for the
ledger/bank files and column mapping in the browser, since a
double-clicked app has no command line to pass --ledger/--bank on.

Still bound to 127.0.0.1 only, per CLAUDE.md.
"""

from __future__ import annotations

import socket
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from recwise.web import create_app

HOST = "127.0.0.1"
PREFERRED_PORT = 5000


class _PortProbe(Protocol):
    """What _pick_port needs from a socket -- narrowed so tests can fake
    one without opening a real network-capable socket (this repo's test
    suite blocks AF_INET/AF_INET6 sockets outright, see conftest.py)."""

    def bind(self, address: tuple[str, int]) -> None: ...
    def getsockname(self) -> tuple[str, int]: ...
    def __enter__(self) -> _PortProbe: ...
    def __exit__(self, *exc_info: object) -> None: ...


def _default_probe() -> _PortProbe:
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def data_dir() -> Path:
    """Per-user directory the packaged app stores uploads and output in.

    A double-clicked app has no --out-dir flag to take this from.
    """
    return Path.home() / "Recwise"


def _pick_port(probe_factory: Callable[[], _PortProbe] = _default_probe) -> int:
    """Prefer PREFERRED_PORT; fall back to any free port if it's taken.

    Best-effort only: another process could still grab the chosen port
    between this check and app.run() actually binding it, in which case
    app.run() raises -- acceptable for a single-user local tool.
    """
    with probe_factory() as probe:
        try:
            probe.bind((HOST, PREFERRED_PORT))
            return PREFERRED_PORT
        except OSError:
            pass
    with probe_factory() as fallback:
        fallback.bind((HOST, 0))
        port: int = fallback.getsockname()[1]
        return port


def main() -> int:
    out_dir = data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(out_dir=out_dir)
    port = _pick_port()
    url = f"http://{HOST}:{port}/"

    print(f"Recwise is running at {url}")
    print("Close this window (or press Ctrl+C) to stop Recwise.")
    webbrowser.open(url)

    try:
        app.run(host=HOST, port=port, debug=False)
    except KeyboardInterrupt:
        print("Recwise stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
