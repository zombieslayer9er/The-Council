# Secure Cloudflare Tunnel path

Use a remotely managed, named Cloudflare Tunnel when the static dashboard must reach the local
Council API from another device. The API remains bound to `127.0.0.1:8000`; `cloudflared` makes
outbound connections to Cloudflare, so this design does not require a router port-forward or an
inbound Windows Firewall rule.

This route has two independent authorization gates:

1. Cloudflare Access admits only the configured identity to the API hostname.
2. Council mutation routes still require the local `BOTNET_COUNCIL_CONTROL_TOKEN` bearer token.

CORS is a browser boundary, not authentication. It is intentionally exact-match and does not
replace either gate.

## Account prerequisites

- An active Cloudflare DNS zone for a domain you control.
- Cloudflare Zero Trust/Access enabled with an identity provider. One-time PIN is sufficient for
  a single operator when its policy permits only that operator's email address.
- `cloudflared` installed on the Windows computer running the API.

Do not use a random `trycloudflare.com` quick tunnel for this path. Quick tunnels are intended for
testing and cannot provide the named hostname and Access policy described here.

## Cloudflare resources

Create a remotely managed tunnel named `botnet-council-api` and configure exactly these ingress
rules, substituting a hostname in your zone:

```yaml
ingress:
  - hostname: council-api.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Create a proxied CNAME from that hostname to `<TUNNEL_ID>.cfargotunnel.com`. Protect the exact
hostname with a self-hosted Access application and an Allow policy limited to the intended
identity. In the Access application's CORS settings, bypass only OPTIONS requests to the origin;
FastAPI then answers the preflight using the exact origin allowlist. Do not bypass Access for any
data or control path.

The browser must first visit `https://council-api.example.com/api/health` and complete the Access
login. The dashboard then sends the Access cookie on cross-origin REST requests. Some private
browsing modes block third-party cookies; test in a normal browser session.

## Local process configuration

Set secrets only in the process environment or an OS secret manager. Never commit them:

```powershell
$env:BOTNET_COUNCIL_BROWSER_ORIGINS = 'https://botnet-council.smithphotography2020.chatgpt.site'
$env:BOTNET_COUNCIL_CONTROL_TOKEN = '<at-least-32-random-characters>'
botnet-council-api
```

In a separate terminal, run the remotely managed tunnel with its token:

```powershell
$env:TUNNEL_TOKEN = '<Cloudflare tunnel token>'
cloudflared tunnel --no-autoupdate run --token $env:TUNNEL_TOKEN
```

The frontend already derives `wss://` from an HTTPS backend base. Build the static artifact with
the tunnel hostname before publishing it:

```powershell
Set-Location web
$env:VITE_API_BASE_URL = 'https://council-api.example.com'
pnpm build
```

`VITE_API_BASE_URL` is public build configuration, not a secret. The Council control token and
tunnel token must never use a `VITE_` variable because Vite embeds those values in browser assets.

## Verification

1. Confirm the API still listens only on `127.0.0.1:8000`.
2. Confirm an unauthenticated request to the public hostname receives the Access login boundary.
3. Authenticate on the phone, then load `/api/health` and the dashboard.
4. Confirm a foreign `Origin` receives no CORS permission.
5. Confirm a control request without the Council bearer token is rejected.
6. Confirm the dashboard's event socket uses `wss://` and receives ordered events.
7. Stop `cloudflared` and confirm the public hostname can no longer reach the origin.

If a cross-origin POST fails at preflight, verify that Access bypasses OPTIONS only and that its
CORS configuration agrees with the API's allowed origin, methods, headers, and credentials.
