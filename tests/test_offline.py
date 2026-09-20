import socket

import pytest
from conftest import NetworkAccessError


def test_socket_creation_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.socket()


def test_create_connection_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("example.invalid", 80))
