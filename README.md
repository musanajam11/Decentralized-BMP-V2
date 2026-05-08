# Decentralized-BMP V2

A self-hostable, security-focused alternative backend for [BeamMP](https://beammp.com) — the multiplayer mod for BeamNG.drive — designed to be discovered through the [BeamNG Mod Registry (BMR)](https://bmr.musanet.xyz) by clients such as [BeamNG Content Manager](https://bmr.musanet.xyz).

> **Why?** Run your own BeamMP backend with your own users, your own keys, and your own moderation policy — and (optionally) have it listed on a community index that Content Manager can browse, without giving up control of the server.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React-informational)
![Docker](https://img.shields.io/badge/deploy-docker--compose-2496ED)

[![See it in action — bmp.musanet.xyz](https://img.shields.io/badge/See%20it%20in%20action-bmp.musanet.xyz-1971c2?style=for-the-badge&logo=react&logoColor=white)](https://bmp.musanet.xyz)

---

## Highlights

- **Hardened auth** — Argon2id password hashing, JWT access + refresh tokens, per-IP and per-account rate limits, optional Cloudflare Turnstile on login/register, optional Discord & GitHub OAuth.
- **Per-user key allotment** — admins set how many server keys each new account can mint, with per-user overrides.
- **Content Manager integration** — flip one switch and your backend is announced to BMR every 60 s. CM's backend picker discovers it; users add it with one click.
- **Upgrade-resilient** — the BeamMP-facing surface (`/v/s`, builds, heartbeat, `/userlogin`, `/pkToUser`) sits behind a versioned `compat/` shim, so newer official BeamMP-Server / BeamMP-Launcher releases drop in without recompiling the backend.
- **Modern UI** — React + Mantine, dark/light toggle, mobile-friendly admin dashboard.
- **Single-binary deploy** — one `docker compose up -d` brings up backend + frontend + proxy on one host port.


---

## How it integrates with Content Manager

```
   ┌────────────────────────┐
   │  Your V2 backend       │  ── POST /api/backends/heartbeat ──▶  ┌──────────────────────┐
   │  bmp.example.xyz       │     { url, name, region, players }    │  BMR                 │
   └────────────────────────┘     (every 60s, if publishing on)     │  bmr.musanet.xyz     │
                                                                    └──────────┬───────────┘
                                                                               │ GET /api/backends
                                                                               ▼
                                                                    ┌──────────────────────┐
                                                                    │  Content Manager     │
                                                                    │  (desktop client)    │
                                                                    │  → backend picker    │
                                                                    └──────────────────────┘
```

Publishing is **opt-in and reversible**:

- **Off** — backend is reachable only at its own `PUBLIC_ORIGIN`. Anyone with the URL can register / log in / mint keys, but it never appears in CM's picker.
- **On** — backend POSTs a small heartbeat to BMR every 60 s containing only operator-approved fields (URL, display name, region, region, current public-server count). Stop publishing and BMR expires the entry within minutes.

Operator endpoints (admin-only):

| Endpoint | Purpose |
| --- | --- |
| `GET /publish/status` | Toggle state, BMR URL, configured/enabled flags, public-server count |
| `PATCH /publish/status` | `{ "enabled": true \| false }` runtime toggle |
| `POST /publish/push` | Force one heartbeat (returns BMR's reason code — useful for diagnostics) |


---

## Security model

V2 was rebuilt from the ground up to be safe to expose to the public internet.

| Layer | What it does |
| --- | --- |
| **Password hashing** | Argon2id (`argon2-cffi`) with sane defaults — no SHA, no MD5, no bcrypt downgrade path |
| **Session tokens** | Short-lived JWT access (15 min) + long-lived refresh (30 d), HMAC-signed with a per-deploy secret |
| **Rate limiting** | Sliding-window per-IP limiter on `/auth/*` routes (30 req / 60 s) on top of per-account lockouts |
| **Bot mitigation** | Optional [Cloudflare Turnstile](https://www.cloudflare.com/products/turnstile/) on login & registration |
| **HTTP hardening** | CSP (Turnstile-aware), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS on HTTPS |
| **CORS** | Strict allow-list driven by `ALLOWED_ORIGINS` |
| **No code-injection ports** | The backend exposes only HTTP; `/data` is a plain volume, no shell-out endpoints |
| **Secrets via env** | Nothing baked into the image; `.env` is git-ignored |

The bootstrap admin account is created **only** when the users table is empty, and you are expected to change its password on first login.


---

## Architecture

```
Decentralized-BMP-V2/
├── backend/                  FastAPI app
│   ├── app/
│   │   ├── main.py           Entry point, middlewares, lifespan
│   │   ├── settings.py       Pydantic settings (env-driven)
│   │   ├── db.py             SQLite (WAL) + migrations
│   │   ├── security.py       Argon2 + JWT helpers
│   │   ├── publisher.py      BMR heartbeat loop
│   │   ├── turnstile.py      Cloudflare Turnstile verification
│   │   ├── compat/           Versioned BeamMP protocol shims
│   │   └── routers/          auth, admin, keys, invites, messages,
│   │                         publish, oauth, beammp, builds, compat_v1
│   ├── scripts/
│   │   ├── entrypoint.sh
│   │   └── fetch_builds.sh   Downloads patched BeamMP binaries from rolling release
│   └── Dockerfile
├── frontend/                 Vite + React + Mantine SPA
│   ├── src/
│   │   ├── api.ts            Fetch wrapper with refresh-token logic
│   │   ├── auth.tsx          Auth context
│   │   └── pages/            Login, Dashboard, Keys, Invites,
│   │                         Messages, Publish, Admin, Downloads
│   └── nginx.conf            In-container static-file server
├── docker-compose.yml        backend + frontend + nginx proxy
├── .env.example              Copy → .env, fill in
└── LICENSE                   AGPL-3.0
```

**Stack**

- Backend — Python 3.12, FastAPI 0.115, Pydantic v2, SQLite (WAL mode), Authlib (OAuth), Argon2-CFFI, PyJWT, httpx
- Frontend — React 18, Mantine 7, TanStack Query, React Router 6, Vite 5
- Proxy — `nginx:1.27-alpine`, single-host routing


---

## Quick start (Docker)

**Requirements:** Docker Engine 24+ with Compose v2.20+ (for `pull_policy: build`).

```bash
git clone https://github.com/musanajam11/Decentralized-BMP-V2.git
cd Decentralized-BMP-V2
cp .env.example .env
# edit .env — at minimum set JWT_SECRET, BOOTSTRAP_ADMIN_*, and PUBLIC_ORIGIN
docker compose up -d
```

Then point a reverse proxy (Cloudflare Tunnel, NPM, SWAG, Traefik, …) at host port `8420` for your public domain. The bundled `proxy` service routes API paths to the backend and everything else to the SPA, so the entire stack only needs **one** public port.

First login:

1. Open `https://your-domain/`
2. Log in with `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD`
3. **Change the admin password.**
4. Optional: enable publishing on the **Publish** page to appear in BMR / Content Manager.


---

## Configuration

All settings come from `.env`. See [`.env.example`](.env.example) for the full annotated list. Most-used keys:

| Variable | Purpose |
| --- | --- |
| `PUBLIC_ORIGIN` | Public URL the backend is reached at (used in OAuth callbacks, BMR heartbeat, etc.) |
| `ALLOWED_ORIGINS` | Comma-separated CORS allow-list |
| `JWT_SECRET` | 32+ random bytes — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | Initial admin (created only if no users exist) |
| `DEFAULT_KEY_ALLOTMENT` | Server keys a brand-new account may mint |
| `LAUNCHER_VERSION` / `SERVER_VERSION` / `COMPAT_PROFILE` | Version negotiation surface for BeamMP clients |
| `PUBLISH_ENABLED`, `BMR_API_KEY`, `PUBLISH_DISPLAY_NAME`, `PUBLISH_REGION`, `PUBLISH_DESCRIPTION` | BMR publishing |
| `DISCORD_*` / `GITHUB_*` / `OAUTH_REDIRECT_BASE` | Optional OAuth providers |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET` | Optional Cloudflare Turnstile |

---

## Upgrading the BeamMP binaries

The version string the launcher sees (`/v/s`) and the binaries served from `/builds/launcher` and `/builds/client` are decoupled from the FastAPI app.

Patched server and launcher binaries are produced by [`.github/workflows/build-binaries.yml`](.github/workflows/build-binaries.yml), which:

- Resolves the latest release tag from `BeamMP/BeamMP-Server` and `BeamMP/BeamMP-Launcher`.
- Clones each repo at that tag and applies [`patches/apply-server-patch.sh`](patches/apply-server-patch.sh) / [`patches/apply-launcher-patch.sh`](patches/apply-launcher-patch.sh). The patches replace hardcoded backend hostnames with reads of `BMP_BACKEND_HOST` (server) and `BMP_BACKEND_URL` (launcher); behaviour is vanilla when the vars are unset.
- Builds via the upstream CMake/vcpkg toolchains (Linux Debian 12 + Windows for the server, Windows for the launcher).
- Publishes all artifacts to a single rolling pre-release on this repo (`binaries-latest`).

`backend/scripts/fetch_builds.sh` runs on container start and pulls those artifacts into `/data/builds/`. To upgrade:

1. Trigger the **build-binaries** workflow (or wait for the daily cron) so a fresh `binaries-latest` is published.
2. Bump `LAUNCHER_VERSION` / `SERVER_VERSION` in `.env`.
3. If the upstream protocol changed, add a new `backend/app/compat/v_<version>.py` adapter and point `COMPAT_PROFILE` at it.
4. `docker compose restart backend` (set `BUILDS_FORCE_REFETCH=1` to re-pull existing files).

No image rebuild is needed for binary-only updates.

Operators running the patched binaries directly must export the matching env var, e.g. `BMP_BACKEND_HOST=bmp.musanet.xyz` for the server or `BMP_BACKEND_URL=https://bmp.musanet.xyz` for the launcher.


---

## Development

```bash
# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload --port 8420

# Frontend (separate shell)
cd frontend
npm install
npm run dev          # Vite dev server on :5173, proxies API to :8420
npm run typecheck    # tsc -b — used in CI
npm run build        # production bundle into frontend/dist
```

The backend creates `./data/dbmp.sqlite` on first run.

---

## License

[GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

The AGPL was chosen specifically because this is **server software**: anyone running a modified V2 backend that users connect to over the network is required to make their modifications available to those users. This keeps the ecosystem honest — every Decentralized-BMP backend the community discovers through Content Manager remains inspectable and forkable.

---

## Acknowledgements

- [BeamMP](https://beammp.com) — the multiplayer mod itself.
- [BeamNG.drive](https://www.beamng.com) — the simulator.
- [BeamNG Mod Registry (BMR)](https://bmr.musanet.xyz) and [BeamNG Content Manager](https://bmr.musanet.xyz) — the discovery + client side of this design.
- The Mantine, FastAPI, and Pydantic communities for being a joy to build on.

---

## Disclaimer

This project is **not affiliated with BeamMP, BeamNG GmbH, or Cloudflare**. "BeamMP" and "BeamNG.drive" are trademarks of their respective owners. Use of this software does not imply endorsement.
