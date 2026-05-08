#!/usr/bin/env sh
# update.sh — apply source/config changes to the running stack.
#
# Run this from /mnt/user/appdata/beammp_backend after copying new files
# from your dev box. It guarantees the frontend image is rebuilt
# (Docker's normal `up -d` will NOT rebuild on source changes), reloads
# the proxy nginx config, and restarts the backend so live-mounted
# Python edits take effect.
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

echo "==> Restarting backend (live-mounts ./backend/app, no rebuild needed)..."
docker compose restart backend

echo "==> Reloading proxy nginx (picks up changes in ./nginx.conf)..."
if docker compose exec -T proxy nginx -t >/dev/null 2>&1; then
  docker compose exec -T proxy nginx -s reload
  echo "    proxy reloaded."
else
  echo "    nginx -t failed; falling back to full restart so you see the error."
  docker compose exec -T proxy nginx -t || true
  docker compose restart proxy
fi

echo "==> Done."
echo "    Browser hard-reload (Ctrl+Shift+R) recommended on the first visit."
