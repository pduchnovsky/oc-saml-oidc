# Omada SAML to OIDC Bridge

Omada SAML to OIDC Bridge lets an Omada Controller accept OIDC login through SATOSA plus a small amount of custom routing and rewrite code. The public browser flow stays on OIDC, while the bridge turns that login into the SAML traffic Omada expects.

It is designed for self-hosted and homelab deployments, with SATOSA and the bridge services running in one Python process and SATOSA using a single worker thread by default.

## How it works

1. The browser goes to the public Omada URL.
2. The Omada launch route sends the browser into SATOSA.
3. SATOSA authenticates the user through the configured OIDC provider.
4. The bridge posts the SAML response back to Omada.
5. The custom proxy layer rewrites public URLs so Omada keeps redirecting to the browser-facing hostname instead of an internal controller address.

## What you need

- A public HTTPS hostname for the bridge
- A public HTTPS hostname for the OIDC provider
- One or more internal Omada controller endpoints
- Docker and Docker Compose
- An OIDC Identity Provider (IdP) such as Pocket ID or Authelia

## Required URL rules

These settings must be correct before the bridge will behave properly:

- `PUBLIC_BASE_URL` must be a public `https://` URL for the bridge itself.
- `OIDC_PROVIDER_ISSUER` must be the public `https://` issuer URL for Pocket ID or Authelia.
- `OMADA_PUBLIC_BASE_URL` must be the public `https://` URL users open for Omada.
- `OMADA_UPSTREAM_BASES` must contain internal controller IPs or DNS names plus port, such as `https://10.0.0.11:443,https://omada-node-2.internal:443`.

Do not point `OMADA_UPSTREAM_BASES` at the public Omada hostname. The bridge uses those upstream values to reach the controller directly inside the network.

## Docker Compose

The compose example in `examples/docker-compose.yml` shows the bridge container. Fill in the placeholders in `examples/omada-saml-oidc.env` with your Omada and OIDC values, and do not commit real credentials.

```yaml
image: ghcr.io/pduchnovsky/oc-saml-oidc:latest
```

The examples use generic hostnames:

- `bridge.example.com` for the public bridge hostname
- `omada.example.com` for the public Omada hostname
- `auth.example.com` for the IdP
- `controller-1.internal` for the private Omada controller node

The compose file defines a shared `omada` Docker network so the bridge and the OIDC provider can talk to each other without exposing the controller upstreams to the public internet.

## Pocket ID setup

Pocket ID works well when you want a light OIDC provider that uses passkeys exclusively.

1. Create an OIDC client for the bridge.
2. Set `OIDC_PROVIDER_ISSUER` to the public Pocket ID issuer URL.
3. Point the browser-facing Omada hostname at the bridge launch hostname.

Use `examples/docker-compose.yml` as the starting point, then attach Pocket ID to the same Docker network and point `OIDC_PROVIDER_ISSUER` at its public issuer URL.

## Authelia setup

Authelia is the right fit when you already use it as your main identity layer.

1. Create an OIDC client for the bridge in Authelia.
2. Set `OIDC_PROVIDER_ISSUER` to the public Authelia issuer URL.
3. Keep the Authelia public URL on HTTPS.
4. Route the Omada hostname to the ACS handler and the launch hostname to the bridge.

Use the same compose file, then attach Authelia to the same Docker network and point `OIDC_PROVIDER_ISSUER` at its public issuer URL.

## Traefik

Use `examples/traefik-pocket-id.yml` when Pocket ID is the OIDC provider, or `examples/traefik-authelia.yml` when Authelia is the OIDC provider.

Both files show the same public flow:

- `omada.example.com/` redirects to the bridge launch path
- `bridge.example.com/launch/omada` goes to the bridge launcher
- `omada.example.com/sso/saml/login` goes to the bridge ACS handler
- The rest of the Omada hostname goes to the controller upstream
- `auth.example.com` goes to the OIDC provider

The public Omada hostname and the login hostname both stay on HTTPS.

## nginx

Use `examples/nginx-pocket-id.conf` for Pocket ID or `examples/nginx-authelia.conf` for Authelia.

Both files show the same flow with nginx:

- Redirect `/` to the bridge launch path
- `bridge.example.com/launch/omada` goes to the bridge launcher
- Proxy `/sso/saml/login` to the bridge
- Proxy the remaining Omada traffic to the controller upstream
- Proxy the OIDC provider hostname to the IdP

Use nginx when you want the routing rules in one place and prefer explicit server blocks over Traefik labels.

## Example files

- `examples/omada-saml-oidc.env`
- `examples/docker-compose.yml`
- `examples/traefik-pocket-id.yml`
- `examples/traefik-authelia.yml`
- `examples/nginx-pocket-id.conf`
- `examples/nginx-authelia.conf`

## License

MIT. See [`LICENSE`](LICENSE).
