"""SATOSA OIDC backend customizations for public bridge callbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:

    class _BaseOpenIDConnectBackend:
        """Type-checking stub for SATOSA's OIDC backend."""

        config: dict[str, Any]
        name: str
        response_endpoint: Any

        def register_endpoints(self) -> list[tuple[str, Any]]:
            """Return endpoints from the base backend.

            Returns:
                Endpoint tuples registered by SATOSA.
            """

else:
    from satosa.backends.openid_connect import OpenIDConnectBackend as _BaseOpenIDConnectBackend


class PrefixedCallbackOpenIDConnectBackend(_BaseOpenIDConnectBackend):
    """Add a public callback route to the standard SATOSA OIDC backend."""

    def register_endpoints(self) -> list[tuple[str, Any]]:
        """Register default SATOSA endpoints plus the public callback.

        Returns:
            Endpoint route tuples including a short callback route when the
            configured redirect URI ends with this backend name.
        """

        endpoints = list(super().register_endpoints())
        redirect_path = urlparse(
            self.config["client"]["client_metadata"]["redirect_uris"][0]
        ).path.strip("/")
        if redirect_path.endswith("/" + self.name):
            endpoints.append((f"^{self.name}$", self.response_endpoint))
        return endpoints
