# Decentralized-BMP V2 — settings
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Centralized configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    public_origin: str = "http://localhost:8420"
    allowed_origins: str = "http://localhost:5173,http://localhost:8420"
    data_dir: Path = Path("/data")

    # --- Auth ---
    jwt_secret: str = "change-me"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "changeme-please"
    default_key_allotment: int = 1

    # --- OAuth ---
    discord_client_id: str = ""
    discord_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    oauth_redirect_base: str = ""

    # --- BeamMP version negotiation ---
    launcher_version: str = "2.7.0"
    server_version: str = "3.9.1"
    compat_profile: str = "v2_7_0"

    # --- Publishing (BMR — BeamNG Mod Registry public backend index) ---
    # When enabled and BMR_API_KEY is set, this backend pushes a heartbeat to
    # BMR every 60 s so it is discoverable from Content Manager. Otherwise the
    # backend is still reachable directly at PUBLIC_ORIGIN by anyone who knows
    # the URL — publishing is purely about being listed on BMR.
    publish_enabled: bool = False
    bmr_url: str = "https://bmr.musanet.xyz"
    bmr_api_key: str = ""
    bmr_heartbeat_path: str = "/api/backends/heartbeat"
    publish_display_name: str = "Decentralized BMP"
    publish_region: str = "us-east"
    publish_description: str = ""

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
