# Decentralized-BMP V2 — compat profile for BeamMP-Launcher 2.7.0 / Server 3.9.1
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Default protocol profile. Adapters for newer upstream versions live in sibling modules."""

from __future__ import annotations


def version_string(launcher_version: str, server_version: str) -> str:
    return f"{launcher_version}\n{server_version}"


def normalize_server(raw: dict) -> dict:
    """Map a raw heartbeat payload to the launcher-facing server record.

    Matches the upstream `/servers-info` response shape exactly:
    - all fields are strings (the launcher / CM frontend treats them as such)
    - `sname` (not `name`) is the canonical name field
    - every field the frontend reads is always present (never undefined)
    so client-side `.length`/`.split`/`.localeCompare` calls don't crash.
    """
    def _s(v, default: str = "") -> str:
        if v is None:
            return default
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    def _b(v) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    sname = raw.get("sname") or raw.get("name") or ""
    ip = _s(raw.get("ip"))
    port = _s(raw.get("port"))
    return {
        "ident": f"{ip}:{port}" if ip and port else "",
        "sname": _s(sname),
        "ip": ip,
        "port": port,
        "players": _s(raw.get("players"), "0"),
        "maxplayers": _s(raw.get("maxplayers"), "0"),
        "map": _s(raw.get("map")),
        "sdesc": _s(raw.get("sdesc") or raw.get("description")),
        "version": _s(raw.get("version")),
        "cversion": _s(raw.get("cversion") or raw.get("clientversion")),
        "tags": _s(raw.get("tags")),
        "owner": _s(raw.get("owner")),
        "official": _b(raw.get("official")),
        "featured": _b(raw.get("featured")),
        "partner": _b(raw.get("partner")),
        "password": _b(raw.get("password") or raw.get("private")),
        "guests": _b(raw.get("guests")),
        "location": _s(raw.get("location")),
        "modlist": _s(raw.get("modlist")),
        "modstotalsize": _s(raw.get("modstotalsize"), "0"),
        "modstotal": _s(raw.get("modstotal"), "0"),
        "playerslist": _s(raw.get("playerslist")),
    }
