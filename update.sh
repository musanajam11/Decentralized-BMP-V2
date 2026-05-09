#!/usr/bin/env sh
# update.sh — apply source/config changes to the running stack.
#
# Run this from /mnt/user/appdata/beammp_backend after copying new files
# from your dev box. It guarantees the frontend image is rebuilt
# (Docker's normal `up -d` will NOT rebuild on source changes), reloads
# the proxy nginx config (only if a `proxy` service is defined in the
# compose file), and restarts the backend so any new files in
# ./backend/app or ./backend/scripts take effect.
#
#   ./update.sh
#
# Re-runnable, idempotent, ~30s end-to-end on a warm cache.

set -eu

cd "$(dirname "$0")"

echo "==> Rebuilding frontend image (picks up changes in ./frontend/src)..."
docker compose build frontend

echo "==> Recreating frontend container with the new image..."
docker compose up -d frontend

echo "==> Recreating backend (picks up entrypoint / fetch_builds changes)..."
# Backend Dockerfile COPYs ./app and ./scripts — must rebuild to pick up
# changes. force-recreate then guarantees the new entrypoint runs and
# fetch_builds.sh re-executes against the latest binaries-latest release.
docker compose build backend
docker compose up -d --force-recreate backend

# Optional proxy reload — only if a `proxy` service exists in the compose
# stack (older deployments had one; current single-container setup does
# not). Never aborts the script.
if docker compose config --services 2>/dev/null | grep -qx proxy; then
  echo "==> Reloading proxy nginx..."
  if docker compose exec -T proxy nginx -t >/dev/null 2>&1; then
    docker compose exec -T proxy nginx -s reload && echo "    proxy reloaded."
  else
    echo "    nginx -t failed; not touching the running proxy. Run:"
    echo "      docker compose exec proxy nginx -t"
  fi
else
  echo "==> No 'proxy' service in docker-compose.yml — skipping nginx reload."
fi

echo "==> Done."
echo "    Browser hard-reload (Ctrl+Shift+R) recommended on the first visit."
