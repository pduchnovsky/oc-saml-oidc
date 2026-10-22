"""Tests for environment-driven bridge configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omada_saml_oidc.config import BridgeConfig, ConfigError, UpstreamConfig, load_config


def valid_env(tmp_path: Path) -> dict[str, str]:
    """Build a valid environment mapping for config tests.

    Args:
        tmp_path: Temporary directory used for generated runtime paths.

    Returns:
        Environment mapping with placeholder-safe values.
    """

    return {
        "PUBLIC_BASE_URL": "https://bridge.example.com",
        "OIDC_PROVIDER_ISSUER": "https://auth.example.com",
        "OIDC_CLIENT_ID": "omada-saml-oidc",
        "OIDC_CLIENT_SECRET": "secret",
        "OMADA_PUBLIC_BASE_URL": "https://omada.example.com",
        "OMADA_UPSTREAM_BASES": "https://controller-1.internal:443,https://controller-2.internal:443",
        "OMADA_ID": "omada-id",
        "OMADA_RESOURCE_ID": "resource-id",
        "DATA_DIR": str(tmp_path / "data"),
        "RUNTIME_DIR": str(tmp_path / "runtime"),
    }


def test_from_env_derives_entity_ids_and_relay_state(tmp_path: Path) -> None:
    """Derive Omada entity IDs and RelayState from env values."""

    config = BridgeConfig.from_env(valid_env(tmp_path))

    assert config.public_base_url == "https://bridge.example.com"
    assert config.omada_public_base_url == "https://omada.example.com"
    assert config.oidc_redirect_uri == "https://bridge.example.com/oidc"
    assert config.relay_state == "cmVzb3VyY2UtaWRfb21hZGEtaWQ="
    assert config.satosa_workers == 1
    assert config.omada_upstreams == (
        UpstreamConfig(
            "https://controller-1.internal:443", "https://controller-1.internal:443/omada-id"
        ),
        UpstreamConfig(
            "https://controller-2.internal:443", "https://controller-2.internal:443/omada-id"
        ),
    )


def test_from_env_requires_https_public_urls(tmp_path: Path) -> None:
    """Reject public and issuer URLs that are not HTTPS."""

    env = valid_env(tmp_path)
    env["PUBLIC_BASE_URL"] = "http://bridge.example.com"

    with pytest.raises(ConfigError, match="PUBLIC_BASE_URL must be an https:// URL"):
        BridgeConfig.from_env(env)


def test_from_env_rejects_public_omada_as_upstream(tmp_path: Path) -> None:
    """Reject an upstream that points at the public Omada hostname."""

    env = valid_env(tmp_path)
    env["OMADA_UPSTREAM_BASES"] = "https://omada.example.com"

    with pytest.raises(ConfigError, match="must use internal Omada"):
        BridgeConfig.from_env(env)


def test_load_config_round_trips_generated_mapping(tmp_path: Path) -> None:
    """Load a generated runtime YAML config."""

    config = BridgeConfig.from_env(valid_env(tmp_path))
    path = tmp_path / "bridge.yaml"
    path.write_text(yaml.safe_dump(config.to_mapping(include_secrets=True)))

    loaded = load_config(path)

    assert loaded == config
