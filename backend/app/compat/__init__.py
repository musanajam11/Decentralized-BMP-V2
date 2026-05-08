# Decentralized-BMP V2 — compat package
"""Per-version BeamMP protocol adapters.

Each module exposes:
  - version_string(launcher_ver: str, server_ver: str) -> str
  - normalize_server(raw_payload: dict) -> dict   # shape returned by /servers-info

To support a new upstream version, add `v_<version>.py` and set
`COMPAT_PROFILE=v_<version>` in .env. No other code changes required.
"""
