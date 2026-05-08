# Security Policy

## Reporting a Vulnerability

If you believe you've found a security issue in Decentralized-BMP V2 — especially anything that could lead to **account takeover, server-key theft, privilege escalation, or remote code execution** — please report it privately rather than opening a public issue.

**Preferred:** use GitHub's [Private Vulnerability Reporting](https://github.com/musanajam11/Decentralized-BMP-V2/security/advisories/new).

You can expect:

- An acknowledgement within **72 hours**.
- A status update within **7 days**.
- A coordinated disclosure once a fix is available.

Please include, where possible:

- The version / commit you tested against.
- A minimal reproduction (HTTP requests, payloads, etc.).
- The impact you believe the issue has.

## Scope

In scope:

- Authentication / authorization bypass on any `/auth/*`, `/admin/*`, `/keys/*`, `/invites/*`, `/messages/*`, `/publish/*`, or `/oauth/*` endpoint.
- JWT handling (signing, verification, refresh).
- Server-key minting, revocation, and ownership checks.
- BMR publish payload integrity (e.g. spoofing another backend's identity).
- Rate-limit / lockout bypass.
- Reflected or stored XSS in the React frontend.
- CSRF on state-changing endpoints.

Out of scope:

- Issues that require a compromised admin account or already-leaked secret.
- Self-DoS via resource exhaustion against your own deployment.
- Vulnerabilities in third-party services (BMR, Cloudflare, BeamMP, BeamNG.drive).
- Missing security headers on `/healthz` or static assets.

## Supported Versions

Only the latest commit on `main` is supported. There is no LTS branch.
