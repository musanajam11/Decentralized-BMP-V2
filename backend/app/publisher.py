# Decentralized-BMP V2 — BMR publish-out worker
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background task that pushes a heartbeat to BMR if publishing is on.

Runs every 60 s. Per-key `public` flag decides which servers are included; the
backend-wide `publish_enabled` toggle decides whether anything is sent at all.
When disabled, the backend is still reachable directly at PUBLIC_ORIGIN —
publishing is purely about being listed in BMR's public backends index.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx

from . import app_settings, db
from .routers import builds as builds_router
from .settings import Settings, get_settings

PUSH_INTERVAL_S = 60


def _public_active_servers() -> list[dict]:
    cutoff = int(time.time()) - 60
    out: list[dict] = []
    with db.cursor() as cur:
        rows = cur.execute(
            """SELECT k.server_name, k.key, s.payload_json, s.last_heartbeat
               FROM server_keys k
               JOIN server_state s ON s.auth_key = k.key
               WHERE k.public = 1 AND s.last_heartbeat > ?""",
            (cutoff,),
        ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except Exception:  # noqa: BLE001
            payload = {}
        # Prefer the actual server name from the heartbeat payload over the
        # operator's key label. BeamMP-Server reports its display name in
        # `name` (modern) or `sname` (older); both can carry color codes
        # (`^6^lFoo`). Fall back to the key label if the heartbeat hasn't
        # populated either yet (e.g. brand-new server, first tick).
        server_name = (
            str(payload.get("name") or payload.get("sname") or "").strip()
            or r["server_name"]
        )
        out.append({
            "name": server_name,
            "players": int(payload.get("players", 0) or 0),
            "max_players": int(payload.get("maxplayers", 0) or 0),
            "map": payload.get("map", ""),
            "ip": payload.get("ip", ""),
            "port": int(payload.get("port", 0) or 0),
            "last_heartbeat": r["last_heartbeat"],
        })
    return out


def _build_payload(settings: Settings) -> dict:
    servers = _public_active_servers()
    base = settings.public_origin.rstrip("/")
    bd = settings.data_dir / "builds"
    builds_payload: dict[str, str] = {}
    # Only advertise server binaries: CM bundles its own launcher and the
    # launcher self-distributes the client mod when joining a server, so
    # re-publishing those just clutters the dropdown with duplicate
    # downloads. Launcher / client files (if present on disk) are still
    # reachable via /builds/launcher and /builds/client for vanilla
    # launcher self-updates.
    for key, fname, route in (
        ("server_windows", builds_router.SERVER_WINDOWS, "/builds/server-windows"),
        ("server_linux", builds_router.SERVER_LINUX, "/builds/server-linux"),
    ):
        if (bd / fname).exists():
            builds_payload[key] = f"{base}{route}"
    return {
        "url": settings.public_origin,
        "name": app_settings.publish_display_name(),
        "region": app_settings.publish_region(),
        "description": app_settings.publish_description(),
        "launcher_version": settings.launcher_version,
        "server_version": settings.server_version,
        "servers": servers,
        "active_servers": len(servers),
        "active_players": sum(s["players"] for s in servers),
        "builds": builds_payload,
        "ts": int(time.time()),
    }


async def _push_bmr(settings: Settings, client: httpx.AsyncClient,
                    body: dict) -> httpx.Response:
    """Push the heartbeat to BMR's public backends index."""
    return await client.post(
        f"{settings.bmr_url.rstrip('/')}{settings.bmr_heartbeat_path}",
        json=body,
        headers={"Authorization": f"Bearer {settings.bmr_api_key}"},
        timeout=10.0,
    )


async def push_once(settings: Settings, client: httpx.AsyncClient) -> dict:
    """Push to BMR if configured + enabled.

    Returns a diagnostic dict (always — never raises) so callers can show
    operators *why* a push didn't go out.
    """
    if not settings.bmr_api_key:
        return {"pushed": False, "reason": "bmr_api_key_unset"}
    if not app_settings.publish_enabled():
        return {"pushed": False, "reason": "publish_disabled"}
    body = _build_payload(settings)
    try:
        resp = await _push_bmr(settings, client, body)
    except Exception as exc:  # noqa: BLE001 - best-effort, retry on next tick
        return {"pushed": False, "reason": "transport_error", "detail": str(exc)}
    if resp.status_code >= 400:
        body_text = resp.text[:500]
        return {
            "pushed": False,
            "reason": f"bmr_status_{resp.status_code}",
            "detail": body_text,
            "public_servers": int(body.get("active_servers", 0)),
        }
    return {
        "pushed": True,
        "reason": "ok",
        "public_servers": int(body.get("active_servers", 0)),
    }


async def run_forever() -> None:
    """Always-on publish loop.

    Intentionally does NOT short-circuit on missing api-key/disabled toggle:
    operators may flip those at runtime via /publish/status, and we want the
    next tick to pick that up without a service restart.
    """
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await push_once(settings, client)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(PUSH_INTERVAL_S)
