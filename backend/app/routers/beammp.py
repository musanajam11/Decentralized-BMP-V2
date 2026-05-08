# Decentralized-BMP V2 — BeamMP-facing compatibility shim
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Endpoints called by the BeamMP-Launcher and BeamMP-Server binaries.

The protocol is selected at startup via `COMPAT_PROFILE` so a single backend
build can support multiple upstream versions (drop-in binary upgrades).
"""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse

from .. import db
from .. import geoip
from ..settings import get_settings

router = APIRouter(tags=["beammp"])


def _profile():
    name = get_settings().compat_profile
    try:
        return importlib.import_module(f"app.compat.{name}")
    except ModuleNotFoundError:
        return importlib.import_module("app.compat.v2_7_0")  # safe default


@router.get("/v/s", response_class=PlainTextResponse)
def version_string() -> str:
    s = get_settings()
    return _profile().version_string(s.launcher_version, s.server_version)


@router.post("/heartbeat")
@router.post("/servers/heartbeat")
# BeamMP-Server v3.9+ posts the heartbeat to a versioned API path,
# `/v/s/heartbeat`, instead of the bare `/heartbeat` the launcher uses.
# Without this alias nginx maps the request to a non-POST location and
# the server logs the dreaded "Backend failed to respond to a heartbeat"
# even though connectivity, TLS, and the auth key are all fine.
@router.post("/v/s/heartbeat")
async def heartbeat(request: Request) -> dict:
    """BeamMP-Server heartbeat.

    The on-the-wire shape varies between server versions / patched builds:
    - Modern BeamMP-Server POSTs **JSON** with a top-level ``uuid`` field
      (the server's auth key) plus ``players``, ``maxplayers``, ``port``,
      ``map``, ``private``, ``version``, ``clientversion``, ``name``,
      ``modlist``, etc. It expects a response of the shape
      ``{"status": "2000"|"200", "code": "...", "msg": "..."}`` and
      treats anything else as a failed heartbeat (the dreaded
      "Backend failed to respond to a heartbeat" warning).
    - Older / form-encoded clients POST ``application/x-www-form-urlencoded``
      with ``key=`` (or ``auth_key=``).

    We accept both shapes and always reply in the modern protocol format.
    """
    body: dict = {}
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return {"status": "400", "code": "bad_request", "msg": "Invalid JSON"}
    else:
        try:
            body = dict(await request.form())
        except Exception:  # noqa: BLE001
            body = {}
        if not body:
            # Some patched builds send JSON with the wrong content-type.
            try:
                raw = (await request.body()).decode("utf-8", errors="replace")
                if raw.strip().startswith("{"):
                    body = json.loads(raw)
            except Exception:  # noqa: BLE001
                pass

    auth_key = (
        body.get("uuid")
        or body.get("key")
        or body.get("auth_key")
        or ""
    )
    if not auth_key:
        # Upstream server requires three string fields: status, code, msg.
        # Missing any one produces "Missing/invalid json members in backend
        # response", and a non-2000/200 status string produces
        # "Backend REFUSED the auth key. Reason: <msg>".
        return {"status": "401", "code": "unauthorized", "msg": "Missing auth key"}

    # Self-reported `ip` is what players connect to (and what we GeoIP).
    # Fall back to the connecting IP (X-Forwarded-For aware) if absent so
    # the country flag still resolves for servers that don't advertise it.
    if not body.get("ip"):
        fwd = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        client_ip = fwd or (request.client.host if request.client else "")
        if client_ip:
            body["ip"] = client_ip

    is_new_session = False
    with db.cursor() as cur:
        row = cur.execute("SELECT id FROM server_keys WHERE key = ?", (auth_key,)).fetchone()
        if not row:
            return {"status": "403", "code": "forbidden", "msg": "Invalid or unregistered auth key"}
        existing = cur.execute(
            "SELECT 1 FROM server_state WHERE auth_key = ?", (auth_key,)
        ).fetchone()
        is_new_session = existing is None
        cur.execute(
            """INSERT INTO server_state (auth_key, payload_json, last_heartbeat)
               VALUES (?, ?, ?)
               ON CONFLICT(auth_key) DO UPDATE SET
                 payload_json=excluded.payload_json,
                 last_heartbeat=excluded.last_heartbeat""",
            (auth_key, json.dumps(body), int(time.time())),
        )
    # BeamMP-Server protocol (THeartbeatThread.cpp, minor branch):
    #   status == "2000" -> "Authenticated!"
    #   status == "200"  -> "Resumed authenticated session!"
    #   anything else    -> "Backend REFUSED the auth key. Reason: <msg>"
    # All three fields (status, code, msg) MUST be present and string-typed
    # or the server logs "Missing/invalid json members in backend response"
    # and treats the heartbeat as failed.
    if is_new_session:
        return {"status": "2000", "code": "ok", "msg": "Authenticated"}
    return {"status": "200", "code": "ok", "msg": "Session resumed"}


@router.get("/servers-info")
def servers_info() -> list[dict]:
    """List of currently-active servers for the launcher."""
    cutoff = int(time.time()) - 60
    out: list[dict] = []
    profile = _profile()
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM server_state WHERE last_heartbeat > ?", (cutoff,)
        ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
            record = profile.normalize_server(payload)
            # GeoIP-fill the location if the server didn't self-report one.
            # Cheap on the hot path: cached in SQLite per-IP for 30 days.
            if not record.get("location"):
                cc = geoip.country_for(record.get("ip") or "")
                if cc:
                    record["location"] = cc
            out.append(record)
        except Exception:  # noqa: BLE001 - never let one bad row 500 the list
            continue
    return out


@router.get("/builds/launcher")
def builds_launcher() -> FileResponse:
    s = get_settings()
    path = Path(s.data_dir) / "builds" / "BeamMP-Launcher.exe"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "launcher binary not provisioned")
    return FileResponse(path, filename="BeamMP-Launcher.exe")


@router.get("/builds/client")
def builds_client() -> FileResponse:
    s = get_settings()
    path = Path(s.data_dir) / "builds" / "BeamMP.zip"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "client mod not provisioned")
    return FileResponse(path, filename="BeamMP.zip")
