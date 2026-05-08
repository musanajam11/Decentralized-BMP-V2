# Decentralized-BMP V2 — GeoIP lookup
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resolve a server IP -> ISO 3166-1 alpha-2 country code.

Uses the free, key-less ip-api.com endpoint (45 req/min/IP). Results are
cached in SQLite for 30 days so the public list endpoint never blocks on
the network for a server we've already seen.

Lookups happen lazily from `/servers-info` so a single bad/slow upstream
call can't take down the heartbeat path.
"""

from __future__ import annotations

import ipaddress
import time

import httpx

from . import db

_CACHE_TTL = 30 * 86400  # 30 days
_HTTP_TIMEOUT = 2.0      # seconds — must stay tight; /servers-info is hot


def _ensure_table() -> None:
    with db.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS geoip_cache (
                ip          TEXT PRIMARY KEY,
                country     TEXT NOT NULL DEFAULT '',
                fetched_at  INTEGER NOT NULL
            )"""
        )


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def _fetch_country(ip: str) -> str:
    """Synchronous HTTP — keep the timeout tiny. Returns '' on any failure."""
    try:
        r = httpx.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,countryCode"},
            timeout=_HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return ""
        data = r.json()
        if data.get("status") != "success":
            return ""
        cc = (data.get("countryCode") or "").strip().upper()
        return cc if len(cc) == 2 else ""
    except Exception:  # noqa: BLE001
        return ""


def country_for(ip: str) -> str:
    """Cached country-code lookup. Returns '' for private/invalid IPs."""
    if not ip or not _is_public(ip):
        return ""
    _ensure_table()
    now = int(time.time())
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT country, fetched_at FROM geoip_cache WHERE ip = ?", (ip,)
        ).fetchone()
        if row and (now - int(row["fetched_at"])) < _CACHE_TTL:
            return row["country"] or ""
    cc = _fetch_country(ip)
    # Always write — caching empties suppresses retry storms when ip-api
    # rate-limits us. Negative cache TTL is the same as positive (30 d);
    # operators can DELETE rows to force a re-lookup.
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO geoip_cache (ip, country, fetched_at)
               VALUES (?, ?, ?)
               ON CONFLICT(ip) DO UPDATE SET
                 country=excluded.country,
                 fetched_at=excluded.fetched_at""",
            (ip, cc, now),
        )
    return cc
