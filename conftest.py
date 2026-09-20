"""Repo-wide test fixtures: enforce the offline guarantee during the test run."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest


class NetworkAccessError(RuntimeError):
    """Raised when test code attempts to touch the network."""


def _blocked_socket(*_args: object, **_kwargs: object) -> None:
    raise NetworkAccessError("network access is disabled during tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(socket, "socket", _blocked_socket)
    monkeypatch.setattr(socket, "create_connection", _blocked_socket)
    yield
