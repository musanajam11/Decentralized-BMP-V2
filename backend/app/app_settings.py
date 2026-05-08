# Decentralized-BMP V2 — runtime app settings
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin-tunable runtime configuration stored in `app_settings`.

Env vars seed the defaults on first boot; from then on the dashboard is the
source of truth. Each setting has a typed accessor so the rest of the code
never deals with raw string blobs from sqlite.
"""

from __future__ import annotations

from typing import Literal

from . import db
from .settings import get_settings

KeyAllotmentMode = Literal["admin_issued", "default_amount"]


DEFAULTS: dict[str, str] = {
    # "true" / "false" — anyone can hit /auth/register without an invite code.
    "open_registration": "false",
    # "admin_issued"   → new users start with key_allotment = 0 (an admin must raise it)
    # "default_amount" → every new account is granted N server keys immediately
    "key_allotment_mode": "admin_issued",
    "key_default_amount": "0",
    # "true" / "false" — if on, this backend pushes its public servers to BMR
    # (BeamNG Mod Registry) so it is discoverable from Content Manager.
    "publish_enabled": "false",
    # Public listing identity advertised to BMR. Env vars seed first boot;
    # admins edit them at runtime from the Publish page.
    "publish_display_name": "",
    "publish_region": "",
    "publish_description": "",

    # --- Cloudflare Turnstile (bot protection on auth forms) ---
    # Public site key + secret key. Both blank disables Turnstile entirely.
    # Mirrors the BMR admin layout: the secret is never echoed back to the UI.
    "turnstile_site_key": "",
    "turnstile_secret_key": "",
    # When site/secret are configured, require a successful challenge on:
    "turnstile_require_login": "true",
    "turnstile_require_register": "true",

    # --- Account protection ---
    # Minimum password length enforced on register + change-password.
    "password_min_length": "12",
    # After N consecutive bad logins the account is locked for M minutes.
    "lockout_max_failures": "10",
    "lockout_minutes": "15",

    # --- Theme / blurred background (admin-tunable) ---
    # Empty URL disables the background entirely.
    "background_url": "",
    # CSS pixels of `filter: blur()` applied to the wallpaper layer.
    "background_blur_px": "14",
    # 0 = no dimming, 100 = fully black. Translated client-side to a
    # CSS brightness() factor.
    "background_dim_pct": "45",
    # "true" = only show the wallpaper on the /login page; "false" = also
    # behind every signed-in page.
    "background_apply_to_auth_only": "false",
}


def _coerce_bool(v: str) -> bool:
    return v.lower() in ("1", "true", "yes", "on")


def seed() -> None:
    """Insert defaults for keys that don't exist yet."""
    s = get_settings()
    seeded = dict(DEFAULTS)
    # Allow .env to seed the very first boot:
    seeded["key_default_amount"] = str(s.default_key_allotment)
    seeded["publish_enabled"] = "true" if s.publish_enabled else "false"
    seeded["publish_display_name"] = s.publish_display_name
    seeded["publish_region"] = s.publish_region
    seeded["publish_description"] = s.publish_description
    with db.cursor() as cur:
        for k, v in seeded.items():
            cur.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, v)
            )


def get_all() -> dict[str, str]:
    with db.cursor() as cur:
        rows = cur.execute("SELECT key, value FROM app_settings").fetchall()
    out = dict(DEFAULTS)
    out.update({r["key"]: r["value"] for r in rows})
    return out


def get(key: str) -> str:
    return get_all().get(key, DEFAULTS.get(key, ""))


def set_many(updates: dict[str, str]) -> None:
    allowed = set(DEFAULTS.keys())
    bad = set(updates) - allowed
    if bad:
        raise ValueError(f"unknown settings: {sorted(bad)}")
    with db.cursor() as cur:
        for k, v in updates.items():
            cur.execute(
                """INSERT INTO app_settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (k, v),
            )


# --- typed accessors --------------------------------------------------------

def open_registration() -> bool:
    return _coerce_bool(get("open_registration"))


def key_allotment_mode() -> KeyAllotmentMode:
    v = get("key_allotment_mode")
    return v if v in ("admin_issued", "default_amount") else "admin_issued"  # type: ignore[return-value]


def key_default_amount() -> int:
    try:
        return max(0, int(get("key_default_amount")))
    except ValueError:
        return 0


def new_user_allotment() -> int:
    """Return the key_allotment a freshly-registered user should receive."""
    return key_default_amount() if key_allotment_mode() == "default_amount" else 0


def publish_enabled() -> bool:
    return _coerce_bool(get("publish_enabled"))


def publish_display_name() -> str:
    v = get("publish_display_name").strip()
    return v or get_settings().publish_display_name


def publish_region() -> str:
    v = get("publish_region").strip()
    return v or get_settings().publish_region


def publish_description() -> str:
    # Description may legitimately be empty — don't fall back to env if the
    # admin explicitly cleared it. We can't distinguish "never set" from
    # "cleared" here, so prefer the stored value as-is.
    return get("publish_description")


# --- Turnstile + lockout + password policy ----------------------------------

def turnstile_site_key() -> str:
    return get("turnstile_site_key").strip()


def turnstile_secret_key() -> str:
    return get("turnstile_secret_key").strip()


def turnstile_configured() -> bool:
    return bool(turnstile_site_key() and turnstile_secret_key())


def turnstile_required_for(action: str) -> bool:
    """action ∈ {'login','register'}. Returns False if Turnstile is unconfigured."""
    if not turnstile_configured():
        return False
    key = "turnstile_require_login" if action == "login" else "turnstile_require_register"
    return _coerce_bool(get(key))


def password_min_length() -> int:
    try:
        return max(8, int(get("password_min_length")))
    except ValueError:
        return 12


def lockout_policy() -> tuple[int, int]:
    """Returns (max_failures, lockout_seconds). 0 max disables lockout."""
    try:
        max_f = max(0, int(get("lockout_max_failures")))
    except ValueError:
        max_f = 10
    try:
        mins = max(1, int(get("lockout_minutes")))
    except ValueError:
        mins = 15
    return max_f, mins * 60


# --- Theme / blurred background --------------------------------------------

def background_url() -> str:
    return get("background_url").strip()


def background_blur_px() -> int:
    try:
        return max(0, min(60, int(get("background_blur_px"))))
    except ValueError:
        return 14


def background_dim_pct() -> int:
    try:
        return max(0, min(90, int(get("background_dim_pct"))))
    except ValueError:
        return 45


def background_apply_to_auth_only() -> bool:
    return _coerce_bool(get("background_apply_to_auth_only"))
