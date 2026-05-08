# Decentralized-BMP V2 — modified-binary downloads
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serve the modified BeamMP-Server / BeamMP-Launcher / client mod from
``$DATA_DIR/builds`` so that users hosting servers behind this backend can
fetch the launcher and server binaries that already point at *this*
backend's ``PUBLIC_ORIGIN`` instead of the official ``backend.beammp.com``.

The ``/sha/launcher``, ``/version/launcher``, ``/builds/launcher`` and
``/builds/client`` paths intentionally mirror the official BeamMP launcher
update protocol so vanilla launchers can self-update against a custom
backend without modification (V1 used the same paths).

Files are placed into ``$DATA_DIR/builds`` either by the Dockerfile's build
step (see ``scripts/fetch_builds.sh``) or by the operator dropping them in
manually. When a file is missing the binary endpoints return 404 and the
SHA endpoint returns ``no_update`` so vanilla launchers don't loop on
download attempts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse

from ..settings import get_settings

router = APIRouter(tags=["builds"])

# Filenames are fixed so the Dockerfile / sysadmin and the router agree on
# the same disk layout. They mirror the upstream BeamMP release artifact
# names to make manual drop-in easy.
SERVER_WINDOWS = "BeamMP-Server.exe"
SERVER_LINUX = "BeamMP-Server.debian.12.x86_64"
LAUNCHER_WINDOWS = "BeamMP-Launcher.exe"
CLIENT_MOD = "BeamMP.zip"


def _builds_dir() -> Path:
    p = get_settings().data_dir / "builds"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _serve(name: str) -> FileResponse | PlainTextResponse:
    p = _builds_dir() / name
    if not p.exists():
        return PlainTextResponse("Build not available", status_code=404)
    return FileResponse(p, filename=name)


# ---------------------------------------------------------------------------
# Vanilla-launcher compatibility endpoints
# ---------------------------------------------------------------------------

@router.get("/sha/launcher")
def sha_launcher() -> PlainTextResponse:
    h = _sha256_file(_builds_dir() / LAUNCHER_WINDOWS)
    return PlainTextResponse(h or "no_update")


@router.get("/version/launcher")
def version_launcher() -> PlainTextResponse:
    return PlainTextResponse(get_settings().launcher_version)


@router.get("/builds/launcher", response_model=None)
def download_launcher() -> FileResponse | PlainTextResponse:
    return _serve(LAUNCHER_WINDOWS)


@router.get("/sha/mod")
def sha_mod() -> PlainTextResponse:
    h = _sha256_file(_builds_dir() / CLIENT_MOD)
    return PlainTextResponse(h or "no_update")


@router.get("/builds/client", response_model=None)
def download_client() -> FileResponse | PlainTextResponse:
    return _serve(CLIENT_MOD)


# ---------------------------------------------------------------------------
# Modified server binaries — these are V2-only additions used by Content
# Manager when the operator picks a non-official backend in the dropdown.
# ---------------------------------------------------------------------------

@router.get("/builds/server-windows", response_model=None)
def download_server_windows() -> FileResponse | PlainTextResponse:
    return _serve(SERVER_WINDOWS)


@router.get("/builds/server-linux", response_model=None)
def download_server_linux() -> FileResponse | PlainTextResponse:
    return _serve(SERVER_LINUX)


@router.get("/builds/manifest")
def builds_manifest() -> dict:
    """Inventory of which builds are currently published from this backend.

    Used by Content Manager (via the BMR heartbeat's ``builds`` field) to
    decide which platforms can be hosted against this backend.

    Only the server binaries are advertised: CM ships its own launcher, and
    the BeamMP launcher distributes the client mod automatically on join,
    so re-publishing those would just be confusing duplicate downloads.
    The launcher / client routes still exist (so a vanilla launcher pointed
    at this backend can self-update if the operator drops the files in
    manually), they simply don't appear in the public manifest.
    """
    s = get_settings()
    base = s.public_origin.rstrip("/")
    bd = _builds_dir()
    items: dict[str, dict] = {}
    for key, fname, route in (
        ("server_windows", SERVER_WINDOWS, "/builds/server-windows"),
        ("server_linux", SERVER_LINUX, "/builds/server-linux"),
    ):
        p = bd / fname
        if p.exists():
            items[key] = {
                "url": f"{base}{route}",
                "filename": fname,
                "size": p.stat().st_size,
                "sha256": _sha256_file(p),
            }
    return {"builds": items, "public_origin": base}
