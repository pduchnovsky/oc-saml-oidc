"""Tests for the low-memory SATOSA WSGI server."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from omada_saml_oidc import satosa_server


def test_main_serves_satosa_on_loopback_with_https_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use one Waitress thread and the public HTTPS scheme for SATOSA."""

    application = object()
    wsgi_module = ModuleType("satosa.wsgi")
    wsgi_module.app = application
    captured: dict[str, object] = {}

    def capture_serve(app: object, **settings: object) -> None:
        """Capture the WSGI server settings instead of opening a socket."""

        captured["app"] = app
        captured.update(settings)

    monkeypatch.setitem(sys.modules, "satosa.wsgi", wsgi_module)
    monkeypatch.setattr(satosa_server, "serve", capture_serve)

    assert satosa_server.main(["--port", "18000", "--threads", "1"]) == 0
    assert captured == {
        "app": application,
        "host": "127.0.0.1",
        "port": 18000,
        "threads": 1,
        "url_scheme": "https",
    }
