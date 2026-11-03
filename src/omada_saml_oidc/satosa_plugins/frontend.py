"""SATOSA SAML frontend customizations for Omada."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    class _BaseSAMLFrontend:
        """Type-checking stub for SATOSA's SAML frontend."""

        name: str

        def _filter_attributes(self, idp: Any, internal_response: Any, context: Any) -> Any:
            """Filter attributes in the base frontend.

            Args:
                idp: SATOSA identity provider instance.
                internal_response: SATOSA internal response object.
                context: SATOSA request context.

            Returns:
                Filtered attributes.
            """

        def _handle_authn_response(self, context: Any, internal_response: Any, idp: Any) -> Any:
            """Handle an authentication response in the base frontend.

            Args:
                context: SATOSA request context.
                internal_response: SATOSA internal response object.
                idp: SATOSA identity provider instance.

            Returns:
                Serialized SATOSA response.
            """

else:
    from satosa.frontends.saml2 import SAMLFrontend as _BaseSAMLFrontend


class OmadaSAMLFrontend(_BaseSAMLFrontend):
    """Adapt the SATOSA SAML frontend for Omada compatibility."""

    def _filter_attributes(self, idp: Any, internal_response: Any, context: Any) -> Any:
        """Return the full attribute map so Omada sees every synthetic claim.

        Args:
            idp: SATOSA identity provider instance.
            internal_response: SATOSA internal response object.
            context: SATOSA request context.

        Returns:
            The complete internal response attribute mapping.
        """

        _ = idp, context
        return internal_response.attributes

    def _handle_authn_response(self, context: Any, internal_response: Any, idp: Any) -> Any:
        """Remove SATOSA response fields that confuse Omada.

        Args:
            context: SATOSA request context.
            internal_response: SATOSA internal response object.
            idp: SATOSA identity provider instance.

        Returns:
            Response produced by SATOSA's standard SAML frontend.
        """

        request_state = context.state.get(self.name)
        if request_state and "resp_args" in request_state:
            request_state["resp_args"]["in_response_to"] = None
            request_state["resp_args"]["name_id_policy"] = None
        mail = internal_response.attributes.get("mail", [])
        if mail:
            from saml2.saml import NAMEID_FORMAT_EMAILADDRESS

            internal_response.subject_id = mail[0]
            internal_response.subject_type = NAMEID_FORMAT_EMAILADDRESS
        return super()._handle_authn_response(context, internal_response, idp)
