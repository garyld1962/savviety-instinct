"""NFR-1 / AC-7 sanity: Slice 1 Instinct CLI opens no outbound sockets.

Slice 1 does not exercise `instinct run`, so this test covers only the
commands available now (`version`, `init`, and the reserved stubs).
Slice 2+ will extend this with a full `instinct run` coverage.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app


class _NetworkBlockedError(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _block_outbound_sockets(monkeypatch: pytest.MonkeyPatch):
    """Refuse every common outbound-network entry point in stdlib.

    Covers raw sockets, `socket.create_connection`, DNS resolution, and
    `gethostbyname`. Higher-level libraries (urllib, http.client, requests)
    all funnel through one of these.

    Slice 1 caveat: this fixture runs at test-setup, so any phone-home at
    module-import time would sneak through. No MVP dep is known to do that;
    Slice 2+ will harden with pytest-socket and a subprocess smoke test.
    """

    def _refuse(*args: object, **kwargs: object) -> None:
        raise _NetworkBlockedError(f"outbound network blocked: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "gethostbyname", _refuse)

    real_socket = socket.socket

    class BlockingSocket(real_socket):  # type: ignore[misc]
        def connect(self, *args, **kwargs):
            _refuse(*args, **kwargs)

        def connect_ex(self, *args, **kwargs):
            _refuse(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", BlockingSocket)
    yield


runner = CliRunner()


def test_version_opens_no_sockets():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "instinct" in result.stdout.lower()


def test_init_opens_no_sockets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / ".instinct" / "config.yaml").exists()


def test_reserved_command_opens_no_sockets():
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 2
