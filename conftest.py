"""Repo-wide test fixtures: enforce the offline guarantee during the test run."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

_real_socket = socket.socket


class NetworkAccessError(RuntimeError):
    """Raised when test code attempts to touch the network."""


def _guarded_socket(
    family: int = socket.AF_INET,
    type: int = socket.SOCK_STREAM,  # noqa: A002 -- matches socket.socket's own signature
    proto: int = 0,
    fileno: int | None = None,
) -> socket.socket:
    # AF_UNIX is local-only inter-process communication (no network stack
    # involved) -- asyncio's event loop needs one internally (its
    # self-pipe), which the TUI's tests exercise via textual's Pilot.
    # Only AF_INET/AF_INET6 (real network-capable sockets) are blocked.
    if family == socket.AF_UNIX:
        return _real_socket(family, type, proto, fileno)
    raise NetworkAccessError("network access is disabled during tests")


def _blocked_connection(*_args: Any, **_kwargs: Any) -> socket.socket:
    raise NetworkAccessError("network access is disabled during tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(socket, "socket", _guarded_socket)
    monkeypatch.setattr(socket, "create_connection", _blocked_connection)
    yield
