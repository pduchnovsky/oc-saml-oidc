"""Tests for the low-memory SATOSA WSGI server."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
from types import ModuleType
from xml.etree import ElementTree

import pytest

from omada_saml_oidc import satosa_server
from omada_saml_oidc.config import BridgeConfig
from omada_saml_oidc.supervisor import prepare_runtime
from tests.test_config import valid_env


def test_runtime_plugins_inherit_from_satosa() -> None:
    """Load real SATOSA dependencies instead of accepting fallback plugin bases."""

    from satosa.backends.base import BackendModule
    from satosa.frontends.base import FrontendModule

    from omada_saml_oidc.satosa_plugins.backend import PrefixedCallbackOpenIDConnectBackend
    from omada_saml_oidc.satosa_plugins.frontend import OmadaSAMLFrontend

    assert issubclass(PrefixedCallbackOpenIDConnectBackend, BackendModule)
    assert issubclass(OmadaSAMLFrontend, FrontendModule)


@pytest.mark.skipif(shutil.which("xmlsec1") is None, reason="SAML startup requires xmlsec1")
def test_generated_config_initializes_real_satosa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initialize real plugins and routing using generated artifacts and offline OIDC metadata."""

    from satosa.proxy_server import make_app
    from satosa.satosa_config import SATOSAConfig
    from werkzeug.test import Client

    config = BridgeConfig.from_env(valid_env(tmp_path))
    runtime = prepare_runtime(config)
    monkeypatch.setenv("OMADA_BRIDGE_CONFIG", str(runtime.bridge_config_path))
    monkeypatch.setenv("SATOSA_STATE_ENCRYPTION_KEY", runtime.secret_path.read_text().strip())
    satosa_config = SATOSAConfig(str(runtime.satosa_config_path))
    satosa_config["BACKEND_MODULES"][0]["config"]["provider_metadata"] = {
        "issuer": config.oidc_provider_issuer,
        "authorization_endpoint": f"{config.oidc_provider_issuer}/authorize",
        "token_endpoint": f"{config.oidc_provider_issuer}/token",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    app = make_app(satosa_config)

    response = Client(app).get("/Saml2IDP/proxy.xml", base_url=config.public_base_url)

    assert response.status_code == 200
    metadata = ElementTree.fromstring(response.data)
    assert metadata.tag == "{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor"
    assert metadata.attrib["entityID"] == f"{config.public_base_url}/Saml2IDP/proxy.xml"


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
