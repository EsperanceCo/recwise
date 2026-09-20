from __future__ import annotations

from recwise.desktop_app import HOST, PREFERRED_PORT, _pick_port, data_dir


def test_data_dir_is_under_home() -> None:
    d = data_dir()
    assert d.name == "Recwise"
    assert d.is_relative_to(d.home())


class _FakeProbe:
    """Stands in for a real socket in tests -- this repo's test suite
    blocks real AF_INET/AF_INET6 sockets outright (see conftest.py), so
    _pick_port's branching is exercised through dependency injection
    instead of an actual bind()."""

    def __init__(self, *, port_taken: bool, fallback_port: int = 54321) -> None:
        self.port_taken = port_taken
        self.fallback_port = fallback_port
        self.bound_to: tuple[str, int] | None = None

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_to = address
        if address[1] == PREFERRED_PORT and self.port_taken:
            raise OSError("address already in use")

    def getsockname(self) -> tuple[str, int]:
        return (HOST, self.fallback_port)

    def __enter__(self) -> _FakeProbe:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def test_pick_port_uses_preferred_port_when_free() -> None:
    probes = [_FakeProbe(port_taken=False)]
    assert _pick_port(lambda: probes.pop(0)) == PREFERRED_PORT


def test_pick_port_falls_back_when_preferred_port_is_taken() -> None:
    fallback = _FakeProbe(port_taken=False, fallback_port=54321)
    probes = [_FakeProbe(port_taken=True), fallback]
    port = _pick_port(lambda: probes.pop(0))
    assert port == 54321
    assert fallback.bound_to == (HOST, 0)
