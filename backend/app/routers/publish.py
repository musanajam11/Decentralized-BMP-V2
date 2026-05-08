# Decentralized-BMP V2 — BMR publish toggle
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operator controls for opting in/out of the public BMR backends index.

This is the *backend-wide* switch — it decides whether this backend talks to
BMR at all. The per-server-key `public` flag (see /keys) decides which
individual servers are listed when publishing is on. When publishing is off,
the backend is still reachable directly at PUBLIC_ORIGIN by anyone with the
URL — publishing is purely about discoverability via Content Manager.
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import app_settings, db, publisher, security
from ..settings import Settings, get_settings

router = APIRouter(prefix="/publish", tags=["publish"])


class PublishStatusOut(BaseModel):
    enabled: bool                     # runtime toggle (PATCHable)
    configured: bool                  # True iff BMR_API_KEY is set
    bmr_url: str
    heartbeat_path: str
    display_name: str
    region: str
    description: str
    public_servers: int               # currently active+public on this backend


class PublishToggleIn(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None
    region: str | None = None
    description: str | None = None


class PublishPushOut(BaseModel):
    pushed: bool                      # True iff a heartbeat was actually sent
    reason: str                       # "ok" | "bmr_api_key_unset" | "publish_disabled" | "transport_error" | "bmr_status_<code>"
    detail: str | None = None         # error body / exception message when pushed=False
    public_servers: int | None = None # how many servers were included in the heartbeat


def _public_count() -> int:
    cutoff = int(time.time()) - 60
    with db.cursor() as cur:
        row = cur.execute(
            """SELECT COUNT(*) AS n FROM server_keys k
               JOIN server_state s ON s.auth_key = k.key
               WHERE k.public = 1 AND s.last_heartbeat > ?""",
            (cutoff,),
        ).fetchone()
    return int(row["n"]) if row else 0


def _current(settings: Settings) -> PublishStatusOut:
    return PublishStatusOut(
        enabled=app_settings.publish_enabled(),
        configured=bool(settings.bmr_api_key),
        bmr_url=settings.bmr_url,
        heartbeat_path=settings.bmr_heartbeat_path,
        display_name=app_settings.publish_display_name(),
        region=app_settings.publish_region(),
        description=app_settings.publish_description(),
        public_servers=_public_count(),
    )


@router.get("/status", response_model=PublishStatusOut)
def status(_: dict = Depends(security.require_admin),
           settings: Settings = Depends(get_settings)) -> PublishStatusOut:
    return _current(settings)


@router.patch("/status", response_model=PublishStatusOut)
def toggle(body: PublishToggleIn,
           _: dict = Depends(security.require_admin),
           settings: Settings = Depends(get_settings)) -> PublishStatusOut:
    updates: dict[str, str] = {}
    if body.enabled is not None:
        updates["publish_enabled"] = "true" if body.enabled else "false"
    if body.display_name is not None:
        updates["publish_display_name"] = body.display_name.strip()[:80]
    if body.region is not None:
        updates["publish_region"] = body.region.strip()[:64]
    if body.description is not None:
        updates["publish_description"] = body.description.strip()[:512]
    if updates:
        app_settings.set_many(updates)
    return _current(settings)


@router.post("/push", response_model=PublishPushOut)
async def push_now(_: dict = Depends(security.require_admin),
                   settings: Settings = Depends(get_settings)) -> PublishPushOut:
    """Force an immediate heartbeat to BMR (subject to enabled + configured).

    Useful for testing the BMR connection without waiting up to 60 s for the
    next scheduled tick. Returns the underlying reason / BMR error so the
    operator can diagnose why their backend isn't appearing in the BMR
    dropdown.
    """
    async with httpx.AsyncClient() as client:
        result = await publisher.push_once(settings, client)
    return PublishPushOut(**result)
