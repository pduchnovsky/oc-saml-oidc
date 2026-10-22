"""Environment and file configuration for Omada SAML to OIDC Bridge."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

DEFAULT_ACS_PATH = "/sso/saml/login"
DEFAULT_DATA_DIR = Path("/data")
DEFAULT_LAUNCH_PATH = "/launch/omada"
DEFAULT_OIDC_BACKEND_NAME = "oidc"
DEFAULT_OIDC_SCOPES = "openid profile email groups"
DEFAULT_ROUTER_PORT = 8080
DEFAULT_INTERNAL_LAUNCHER_PORT = 18080
DEFAULT_INTERNAL_PROXY_PORT = 18081
DEFAULT_INTERNAL_SATOSA_PORT = 18000
DEFAULT_RUNTIME_DIR = Path("/tmp/omada-saml-oidc")


class ConfigError(ValueError):
    """Raised when bridge configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class UpstreamConfig:
    """Describe one internal Omada controller endpoint."""

    base_url: str
    sp_entity_id: str

    def validate(self) -> None:
        """Validate this upstream.

        Raises:
            ConfigError: Raised when the upstream URL or entity ID is invalid.
        """

        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError("OMADA_UPSTREAM_BASES entries must be absolute internal URLs")
        if not self.sp_entity_id:
            raise ConfigError("each Omada upstream must have a matching SP entity ID")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> UpstreamConfig:
        """Build an upstream from a serialized mapping.

        Args:
            mapping: Mapping with ``base_url`` and ``sp_entity_id`` keys.

        Returns:
            A validated upstream config.
        """

        upstream = cls(
            base_url=str(mapping.get("base_url", "")).strip().rstrip("/"),
            sp_entity_id=str(mapping.get("sp_entity_id", "")).strip(),
        )
        upstream.validate()
        return upstream


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    """Collect all runtime settings for the bridge container."""

    public_base_url: str
    oidc_provider_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    omada_public_base_url: str
    omada_id: str
    omada_resource_id: str
    omada_upstreams: tuple[UpstreamConfig, ...]
    data_dir: Path = DEFAULT_DATA_DIR
    runtime_dir: Path = DEFAULT_RUNTIME_DIR
    oidc_backend_name: str = DEFAULT_OIDC_BACKEND_NAME
    oidc_scopes: str = DEFAULT_OIDC_SCOPES
    oidc_redirect_uri: str = ""
    launch_path: str = DEFAULT_LAUNCH_PATH
    acs_path: str = DEFAULT_ACS_PATH
    relay_state: str = ""
    usergroup_template: str = "{{groups.first}}"
    satosa_state_encryption_key: str | None = None
    public_port: int = DEFAULT_ROUTER_PORT
    internal_launcher_port: int = DEFAULT_INTERNAL_LAUNCHER_PORT
    internal_proxy_port: int = DEFAULT_INTERNAL_PROXY_PORT
    internal_satosa_port: int = DEFAULT_INTERNAL_SATOSA_PORT
    satosa_workers: int = 1
    health_timeout_seconds: float = 3.0

    def validate(self) -> None:
        """Validate this complete bridge configuration.

        Raises:
            ConfigError: Raised when a required setting is absent, malformed, or
                points at a public URL where an internal URL is required.
        """

        for field_name, value in {
            "PUBLIC_BASE_URL": self.public_base_url,
            "OIDC_PROVIDER_ISSUER": self.oidc_provider_issuer,
            "OMADA_PUBLIC_BASE_URL": self.omada_public_base_url,
        }.items():
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ConfigError(f"{field_name} must be an https:// URL")

        if not self.oidc_client_id:
            raise ConfigError("OIDC_CLIENT_ID is required")
        if not self.oidc_client_secret:
            raise ConfigError("OIDC_CLIENT_SECRET is required")
        if not self.omada_id:
            raise ConfigError("OMADA_ID is required")
        if not self.omada_resource_id:
            raise ConfigError("OMADA_RESOURCE_ID is required")
        if not self.omada_upstreams:
            raise ConfigError("OMADA_UPSTREAM_BASES must include at least one internal Omada URL")

        public_omada_host = urlsplit(self.omada_public_base_url).hostname
        for upstream in self.omada_upstreams:
            upstream.validate()
            if urlsplit(upstream.base_url).hostname == public_omada_host:
                raise ConfigError(
                    "OMADA_UPSTREAM_BASES must use internal Omada IPs or names, "
                    "not OMADA_PUBLIC_BASE_URL"
                )

        for field_name, value in {
            "OIDC_BACKEND_NAME": self.oidc_backend_name,
            "LAUNCH_PATH": self.launch_path,
            "OMADA_ACS_PATH": self.acs_path,
        }.items():
            if not value:
                raise ConfigError(f"{field_name} must not be empty")
        if not self.launch_path.startswith("/") or not self.acs_path.startswith("/"):
            raise ConfigError("LAUNCH_PATH and OMADA_ACS_PATH must start with '/'")
        if (
            min(
                self.public_port,
                self.internal_launcher_port,
                self.internal_proxy_port,
                self.internal_satosa_port,
            )
            <= 0
        ):
            raise ConfigError("ports must be positive integers")
        if self.satosa_workers <= 0:
            raise ConfigError("SATOSA_WORKERS must be a positive integer")
        if self.health_timeout_seconds <= 0:
            raise ConfigError("HEALTH_TIMEOUT_SECONDS must be positive")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> BridgeConfig:
        """Build a bridge config from environment variables.

        Args:
            environ: Environment mapping to read. Defaults to ``os.environ``.

        Returns:
            A validated bridge config with derived defaults applied.
        """

        source = os.environ if environ is None else environ
        public_base_url = _required(source, "PUBLIC_BASE_URL").rstrip("/")
        omada_public_base_url = _required(source, "OMADA_PUBLIC_BASE_URL").rstrip("/")
        omada_id = _required(source, "OMADA_ID")
        omada_resource_id = _required(source, "OMADA_RESOURCE_ID")
        oidc_backend_name = (
            source.get("OIDC_BACKEND_NAME", DEFAULT_OIDC_BACKEND_NAME).strip().strip("/")
        )
        oidc_redirect_uri = source.get(
            "OIDC_REDIRECT_URI", f"{public_base_url}/{oidc_backend_name}"
        ).rstrip("/")
        relay_state = source.get(
            "OMADA_RELAY_STATE", _default_relay_state(omada_resource_id, omada_id)
        ).strip()

        upstream_bases = _split_csv(_required(source, "OMADA_UPSTREAM_BASES"))
        entity_ids = _split_csv(source.get("OMADA_SP_ENTITY_IDS", ""))
        if entity_ids and len(entity_ids) != len(upstream_bases):
            raise ConfigError(
                "OMADA_SP_ENTITY_IDS must have the same entry count as OMADA_UPSTREAM_BASES"
            )
        if not entity_ids:
            entity_ids = [f"{base.rstrip('/')}/{omada_id}" for base in upstream_bases]

        config = cls(
            public_base_url=public_base_url,
            oidc_provider_issuer=_required(source, "OIDC_PROVIDER_ISSUER").rstrip("/"),
            oidc_client_id=_required(source, "OIDC_CLIENT_ID"),
            oidc_client_secret=_required(source, "OIDC_CLIENT_SECRET"),
            omada_public_base_url=omada_public_base_url,
            omada_id=omada_id,
            omada_resource_id=omada_resource_id,
            omada_upstreams=tuple(
                UpstreamConfig(base_url=base.rstrip("/"), sp_entity_id=entity_id)
                for base, entity_id in zip(upstream_bases, entity_ids, strict=True)
            ),
            data_dir=Path(source.get("DATA_DIR", str(DEFAULT_DATA_DIR))),
            runtime_dir=Path(source.get("RUNTIME_DIR", str(DEFAULT_RUNTIME_DIR))),
            oidc_backend_name=oidc_backend_name,
            oidc_scopes=source.get("OIDC_SCOPES", DEFAULT_OIDC_SCOPES).strip(),
            oidc_redirect_uri=oidc_redirect_uri,
            launch_path=source.get("LAUNCH_PATH", DEFAULT_LAUNCH_PATH).strip(),
            acs_path=source.get("OMADA_ACS_PATH", DEFAULT_ACS_PATH).strip(),
            relay_state=relay_state,
            usergroup_template=source.get("OMADA_USERGROUP_TEMPLATE", "{{groups.first}}").strip(),
            satosa_state_encryption_key=source.get("SATOSA_STATE_ENCRYPTION_KEY"),
            public_port=int(source.get("PUBLIC_PORT", str(DEFAULT_ROUTER_PORT))),
            internal_launcher_port=int(
                source.get("INTERNAL_LAUNCHER_PORT", str(DEFAULT_INTERNAL_LAUNCHER_PORT))
            ),
            internal_proxy_port=int(
                source.get("INTERNAL_PROXY_PORT", str(DEFAULT_INTERNAL_PROXY_PORT))
            ),
            internal_satosa_port=int(
                source.get("INTERNAL_SATOSA_PORT", str(DEFAULT_INTERNAL_SATOSA_PORT))
            ),
            satosa_workers=int(source.get("SATOSA_WORKERS", "1")),
            health_timeout_seconds=float(source.get("HEALTH_TIMEOUT_SECONDS", "3")),
        )
        config.validate()
        return config

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> BridgeConfig:
        """Build a bridge config from a runtime YAML mapping.

        Args:
            mapping: Serialized configuration written by the supervisor.

        Returns:
            A validated bridge config.
        """

        upstreams = tuple(
            UpstreamConfig.from_mapping(item) for item in mapping.get("omada_upstreams", [])
        )
        config = cls(
            public_base_url=str(mapping["public_base_url"]).rstrip("/"),
            oidc_provider_issuer=str(mapping["oidc_provider_issuer"]).rstrip("/"),
            oidc_client_id=str(mapping["oidc_client_id"]),
            oidc_client_secret=str(mapping["oidc_client_secret"]),
            omada_public_base_url=str(mapping["omada_public_base_url"]).rstrip("/"),
            omada_id=str(mapping["omada_id"]),
            omada_resource_id=str(mapping["omada_resource_id"]),
            omada_upstreams=upstreams,
            data_dir=Path(mapping.get("data_dir", DEFAULT_DATA_DIR)),
            runtime_dir=Path(mapping.get("runtime_dir", DEFAULT_RUNTIME_DIR)),
            oidc_backend_name=str(mapping.get("oidc_backend_name", DEFAULT_OIDC_BACKEND_NAME)),
            oidc_scopes=str(mapping.get("oidc_scopes", DEFAULT_OIDC_SCOPES)),
            oidc_redirect_uri=str(mapping.get("oidc_redirect_uri", "")),
            launch_path=str(mapping.get("launch_path", DEFAULT_LAUNCH_PATH)),
            acs_path=str(mapping.get("acs_path", DEFAULT_ACS_PATH)),
            relay_state=str(mapping.get("relay_state", "")),
            usergroup_template=str(mapping.get("usergroup_template", "{{groups.first}}")),
            satosa_state_encryption_key=mapping.get("satosa_state_encryption_key"),
            public_port=int(mapping.get("public_port", DEFAULT_ROUTER_PORT)),
            internal_launcher_port=int(
                mapping.get("internal_launcher_port", DEFAULT_INTERNAL_LAUNCHER_PORT)
            ),
            internal_proxy_port=int(
                mapping.get("internal_proxy_port", DEFAULT_INTERNAL_PROXY_PORT)
            ),
            internal_satosa_port=int(
                mapping.get("internal_satosa_port", DEFAULT_INTERNAL_SATOSA_PORT)
            ),
            satosa_workers=int(mapping.get("satosa_workers", 1)),
            health_timeout_seconds=float(mapping.get("health_timeout_seconds", 3)),
        )
        config.validate()
        return config

    def to_mapping(self, *, include_secrets: bool = True) -> dict[str, Any]:
        """Serialize this config to a YAML-safe mapping.

        Args:
            include_secrets: Whether to include OIDC and SATOSA secrets.

        Returns:
            A mapping that can be written to runtime YAML.
        """

        payload: dict[str, Any] = {
            "public_base_url": self.public_base_url,
            "oidc_provider_issuer": self.oidc_provider_issuer,
            "oidc_client_id": self.oidc_client_id,
            "oidc_client_secret": self.oidc_client_secret if include_secrets else "",
            "omada_public_base_url": self.omada_public_base_url,
            "omada_id": self.omada_id,
            "omada_resource_id": self.omada_resource_id,
            "omada_upstreams": [
                {"base_url": upstream.base_url, "sp_entity_id": upstream.sp_entity_id}
                for upstream in self.omada_upstreams
            ],
            "data_dir": str(self.data_dir),
            "runtime_dir": str(self.runtime_dir),
            "oidc_backend_name": self.oidc_backend_name,
            "oidc_scopes": self.oidc_scopes,
            "oidc_redirect_uri": self.oidc_redirect_uri,
            "launch_path": self.launch_path,
            "acs_path": self.acs_path,
            "relay_state": self.relay_state,
            "usergroup_template": self.usergroup_template,
            "public_port": self.public_port,
            "internal_launcher_port": self.internal_launcher_port,
            "internal_proxy_port": self.internal_proxy_port,
            "internal_satosa_port": self.internal_satosa_port,
            "satosa_workers": self.satosa_workers,
            "health_timeout_seconds": self.health_timeout_seconds,
        }
        if include_secrets:
            payload["satosa_state_encryption_key"] = self.satosa_state_encryption_key
        return payload

    @property
    def config_dir(self) -> Path:
        """Return the generated runtime config directory."""

        return self.runtime_dir / "config"

    @property
    def cert_dir(self) -> Path:
        """Return the persistent certificate directory."""

        return self.data_dir / "certs"

    @property
    def secret_dir(self) -> Path:
        """Return the persistent secret directory."""

        return self.data_dir / "secrets"

    @property
    def state_secret_path(self) -> Path:
        """Return the persistent SATOSA state key path."""

        return self.secret_dir / "satosa_state_encryption_key"

    @property
    def frontend_key_path(self) -> Path:
        """Return the persistent SATOSA SAML signing key path."""

        return self.cert_dir / "frontend.key"

    @property
    def frontend_cert_path(self) -> Path:
        """Return the persistent SATOSA SAML signing cert path."""

        return self.cert_dir / "frontend.crt"

    @property
    def bridge_config_path(self) -> Path:
        """Return the generated bridge runtime config path."""

        return self.config_dir / "bridge.yaml"

    @property
    def satosa_config_path(self) -> Path:
        """Return the generated SATOSA proxy config path."""

        return self.config_dir / "proxy_conf.yaml"

    @property
    def satosa_internal_attributes_path(self) -> Path:
        """Return the generated SATOSA internal attributes path."""

        return self.config_dir / "internal_attributes.yaml"

    @property
    def satosa_backend_path(self) -> Path:
        """Return the generated SATOSA OIDC backend path."""

        return self.config_dir / "openid_backend.yaml"

    @property
    def satosa_frontend_path(self) -> Path:
        """Return the generated SATOSA SAML frontend path."""

        return self.config_dir / "saml2_frontend.yaml"

    @property
    def satosa_microservice_path(self) -> Path:
        """Return the generated SATOSA Omada attribute microservice path."""

        return self.config_dir / "omada_attributes.yaml"

    @property
    def satosa_metadata_path(self) -> Path:
        """Return the generated Omada SP metadata path."""

        return self.config_dir / "omada-sp.xml"

    @property
    def router_address(self) -> tuple[str, int]:
        """Return the public router bind address."""

        return "0.0.0.0", self.public_port

    @property
    def acs_url(self) -> str:
        """Return the public Omada ACS URL."""

        return f"{self.omada_public_base_url}{self.acs_path}"

    @property
    def sso_redirect_url(self) -> str:
        """Return the SATOSA SAML redirect endpoint URL."""

        return f"{self.public_base_url}/{self.oidc_backend_name}/sso/redirect"


def load_config(path: Path) -> BridgeConfig:
    """Load a generated bridge runtime config file.

    Args:
        path: YAML file path to read.

    Returns:
        A validated bridge config.
    """

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, Mapping):
        raise ConfigError("runtime config must be a mapping")
    return BridgeConfig.from_mapping(data)


def _required(environ: Mapping[str, str], name: str) -> str:
    """Read a required environment variable.

    Args:
        environ: Environment mapping to read.
        name: Variable name to fetch.

    Returns:
        The stripped variable value.

    Raises:
        ConfigError: Raised when the value is absent or blank.
    """

    value = environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated environment value.

    Args:
        value: Comma-separated text.

    Returns:
        Non-empty stripped entries.
    """

    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def _default_relay_state(resource_id: str, omada_id: str) -> str:
    """Build Omada's default RelayState value.

    Args:
        resource_id: Omada Resource ID.
        omada_id: Omada ID.

    Returns:
        Base64 encoded ``resource_id_omada_id`` text.
    """

    return base64.b64encode(f"{resource_id}_{omada_id}".encode()).decode("ascii")
