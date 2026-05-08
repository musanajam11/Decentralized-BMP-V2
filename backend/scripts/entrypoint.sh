#!/usr/bin/env bash
# Decentralized-BMP V2 — container entrypoint
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Runs build fetch/patch (best-effort, never blocks startup) and then
# execs the container CMD (uvicorn).
set -e

if [[ -x /app/scripts/fetch_builds.sh ]]; then
  /app/scripts/fetch_builds.sh || echo "[entrypoint] fetch_builds.sh failed; continuing without builds" >&2
fi

exec "$@"
