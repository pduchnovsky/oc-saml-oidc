"""Tests for the low-memory SATOSA WSGI server."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from omada_saml_oidc import satosa_server


def test_main_serves_satosa_on_loopback_with_https_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run and close SATOSA's Waitress server with the configured settings."""

    application = object()
    wsgi_module = ModuleType("satosa.wsgi")
    wsgi_module.app = application
    captured: dict[str, object] = {}

    class FakeDispatcher:
        """Capture dispatcher shutdown without creating worker threads."""

        def shutdown(self, timeout: float) -> None:
            """Record the configured request-drain timeout."""

            captured["shutdown_timeout"] = timeout

    class FakeServer:
        """Capture server run and close calls."""

        task_dispatcher = FakeDispatcher()

        def run(self) -> None:
            """Record that Waitress was started."""

            captured["ran"] = True

        def close(self) -> None:
            """Record that the Waitress listener was closed."""

            captured["closed"] = True

    def capture_create_server(app: object, **settings: object) -> FakeServer:
        """Capture server settings instead of opening a socket."""

        captured["app"] = app
        captured.update(settings)
        return FakeServer()

    monkeypatch.setitem(sys.modules, "satosa.wsgi", wsgi_module)
    monkeypatch.setattr(satosa_server, "create_waitress_server", capture_create_server)

    assert satosa_server.main(["--port", "18000", "--threads", "1"]) == 0
    assert captured == {
        "app": application,
        "host": "127.0.0.1",
        "port": 18000,
        "threads": 1,
        "url_scheme": "https",
        "ran": True,
        "shutdown_timeout": 5,
        "closed": True,
    }
