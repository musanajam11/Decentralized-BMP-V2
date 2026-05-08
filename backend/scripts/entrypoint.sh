#!/usr/bin/env bash
# Decentralized-BMP V2 — container entrypoint
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Runs build fetch (best-effort, never blocks startup) and then
# execs the container CMD (uvicorn).
set -e

# The patched BeamMP-Server binary reads $BMP_BACKEND_HOST at runtime
# (and the launcher reads $BMP_BACKEND_URL). Derive both from
# PUBLIC_ORIGIN when not explicitly set, so any sub-process spawned
# from this container — current or future — points back at us instead
# of the official beammp.com infra.
if [[ -z "${BMP_BACKEND_HOST:-}" && -n "${PUBLIC_ORIGIN:-}" ]]; then
  # Strip scheme + any path/port; keep host only.
  _host="${PUBLIC_ORIGIN#*://}"
  _host="${_host%%/*}"
  _host="${_host%%:*}"
  if [[ -n "${_host}" ]]; then
    export BMP_BACKEND_HOST="${_host}"
    echo "[entrypoint] BMP_BACKEND_HOST=${BMP_BACKEND_HOST} (derived from PUBLIC_ORIGIN)"
  fi
fi

if [[ -z "${BMP_BACKEND_URL:-}" && -n "${PUBLIC_ORIGIN:-}" ]]; then
  export BMP_BACKEND_URL="${PUBLIC_ORIGIN%/}"
  echo "[entrypoint] BMP_BACKEND_URL=${BMP_BACKEND_URL} (derived from PUBLIC_ORIGIN)"
fi

if [[ -x /app/scripts/fetch_builds.sh ]]; then
  /app/scripts/fetch_builds.sh || echo "[entrypoint] fetch_builds.sh failed; continuing without builds" >&2
fi

exec "$@"
