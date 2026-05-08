#!/usr/bin/env bash
# Decentralized-BMP V2 — populate $DATA_DIR/builds with patched binaries.
#
# Source: this repo's rolling pre-release (tag `binaries-latest`), produced
# by .github/workflows/build-binaries.yml from upstream BeamMP/BeamMP-Server
# and BeamMP/BeamMP-Launcher with patches/apply-*-patch.sh applied. The
# binaries embed no hostnames; the operator's host is supplied via env at
# runtime:
#
#   BeamMP-Server   reads   $BMP_BACKEND_HOST   (e.g. "bmp.musanet.xyz")
#   BeamMP-Launcher reads   $BMP_BACKEND_URL    (e.g. "https://bmp.musanet.xyz")
#
# The vanilla BeamMP client mod (BeamMP.zip) needs no patching and is
# fetched from upstream as-is.
#
# Env vars:
#   DATA_DIR                   — default /data
#   BUILDS_RELEASE_REPO        — default musanajam11/Decentralized-BMP-V2
#   BUILDS_RELEASE_TAG         — default binaries-latest
#   BUILDS_SERVER_LINUX_URL    — override single artifact URL
#   BUILDS_SERVER_WINDOWS_URL  — override single artifact URL
#   BUILDS_LAUNCHER_URL        — override single artifact URL
#   BUILDS_CLIENT_URL          — override single artifact URL
#   BUILDS_FORCE_REFETCH=1     — re-download even if file already on disk
#   SKIP_BUILDS_FETCH=1        — skip everything (operator drops files manually)

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
BUILDS_DIR="${DATA_DIR}/builds"
mkdir -p "${BUILDS_DIR}"

if [[ "${SKIP_BUILDS_FETCH:-0}" == "1" ]]; then
  echo "[fetch_builds] SKIP_BUILDS_FETCH=1 — skipping download"
  exit 0
fi

RELEASE_REPO="${BUILDS_RELEASE_REPO:-musanajam11/Decentralized-BMP-V2}"
RELEASE_TAG="${BUILDS_RELEASE_TAG:-binaries-latest}"
RELEASE_BASE="https://github.com/${RELEASE_REPO}/releases/download/${RELEASE_TAG}"

CLIENT_URL="${BUILDS_CLIENT_URL:-https://github.com/BeamMP/BeamMP/releases/latest/download/BeamMP.zip}"
SERVER_LIN_URL="${BUILDS_SERVER_LINUX_URL:-${RELEASE_BASE}/BeamMP-Server.debian.12.x86_64}"
SERVER_WIN_URL="${BUILDS_SERVER_WINDOWS_URL:-${RELEASE_BASE}/BeamMP-Server.exe}"
LAUNCHER_URL="${BUILDS_LAUNCHER_URL:-${RELEASE_BASE}/BeamMP-Launcher.exe}"

fetch() {
  local url="$1" dest="$2"
  if [[ -s "${dest}" && "${BUILDS_FORCE_REFETCH:-0}" != "1" ]]; then
    echo "[fetch_builds] keep ${dest##*/} ($(stat -c%s "${dest}") bytes)"
    return
  fi
  echo "[fetch_builds] download ${url}"
  if ! curl -fsSL --retry 3 --retry-delay 2 --max-time 600 \
       -o "${dest}.part" "${url}"; then
    echo "[fetch_builds] FAILED to download ${url} — leaving previous file in place" >&2
    rm -f "${dest}.part"
    return
  fi
  mv "${dest}.part" "${dest}"
  echo "[fetch_builds] saved ${dest} ($(stat -c%s "${dest}") bytes)"
}

fetch "${SERVER_LIN_URL}" "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64"
fetch "${SERVER_WIN_URL}" "${BUILDS_DIR}/BeamMP-Server.exe"
fetch "${LAUNCHER_URL}"   "${BUILDS_DIR}/BeamMP-Launcher.exe"
fetch "${CLIENT_URL}"     "${BUILDS_DIR}/BeamMP.zip"

# Linux server is delivered without exec bit through plain HTTP.
if [[ -s "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64" ]]; then
  chmod +x "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64"
fi

echo "[fetch_builds] done"
