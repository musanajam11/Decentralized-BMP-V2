#!/usr/bin/env bash
# Decentralized-BMP V2 — populate $DATA_DIR/builds with patched binaries
# pre-targeted at THIS backend's domain.
#
# Source: this repo's rolling pre-release (tag `binaries-latest`), produced
# by .github/workflows/build-binaries.yml from upstream BeamMP/BeamMP-Server
# and BeamMP/BeamMP-Launcher with patches/apply-*-patch.sh applied. Those
# binaries ship host-agnostic (an empty 256-byte sentinel-led host slot in
# .rodata; vanilla fallback to backend.beammp.com if launched as-is).
#
# This script downloads the generic artifacts then byte-patches the host
# slot in-place with this deployment's own host (derived from
# PUBLIC_ORIGIN, or supplied via BMP_BACKEND_HOST). Operators downloading
# the resulting binary from /builds/... get a fully turnkey executable —
# no env vars, no wrapper scripts.
#
# The vanilla BeamMP client mod (BeamMP.zip) needs no patching and is
# fetched from upstream as-is.
#
# Env vars:
#   DATA_DIR                   — default /data
#   PUBLIC_ORIGIN              — REQUIRED; e.g. https://bmp.musanet.xyz
#   BMP_BACKEND_HOST           — override host derived from PUBLIC_ORIGIN
#   BUILDS_RELEASE_REPO        — default musanajam11/Decentralized-BMP-V2
#   BUILDS_RELEASE_TAG         — default binaries-latest
#   BUILDS_SERVER_LINUX_URL    — override single artifact URL
#   BUILDS_SERVER_WINDOWS_URL  — override single artifact URL
#   BUILDS_LAUNCHER_URL        — override single artifact URL
#   BUILDS_CLIENT_URL          — override single artifact URL
#   BUILDS_FORCE_REFETCH=1     — re-download even if file already on disk
#   BUILDS_SKIP_HOST_PATCH=1   — fetch unmodified (debug only)
#   SKIP_BUILDS_FETCH=1        — skip everything

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
BUILDS_DIR="${DATA_DIR}/builds"
mkdir -p "${BUILDS_DIR}"

if [[ "${SKIP_BUILDS_FETCH:-0}" == "1" ]]; then
  echo "[fetch_builds] SKIP_BUILDS_FETCH=1 — skipping download"
  exit 0
fi

# Resolve the host this backend is reachable on. Strip scheme/port/path
# down to just the bare hostname so the patched binary points at the
# right thing regardless of how PUBLIC_ORIGIN is written.
HOST="${BMP_BACKEND_HOST:-}"
if [[ -z "${HOST}" && -n "${PUBLIC_ORIGIN:-}" ]]; then
  HOST="${PUBLIC_ORIGIN#http://}"
  HOST="${HOST#https://}"
  HOST="${HOST%%/*}"
fi
if [[ -z "${HOST}" && "${BUILDS_SKIP_HOST_PATCH:-0}" != "1" ]]; then
  echo "::error::neither PUBLIC_ORIGIN nor BMP_BACKEND_HOST is set — patched binary cannot be host-stamped" >&2
  exit 1
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
    return 0
  fi
  echo "[fetch_builds] download ${url}"
  if ! curl -fsSL --retry 3 --retry-delay 2 --max-time 600 \
       -o "${dest}.part" "${url}"; then
    echo "[fetch_builds] FAILED to download ${url} — leaving previous file in place" >&2
    rm -f "${dest}.part"
    return 1
  fi
  mv "${dest}.part" "${dest}"
  echo "[fetch_builds] saved ${dest} ($(stat -c%s "${dest}") bytes)"
}

# Stamp HOST into the 256-byte sentinel-led slot inside a patched binary.
# Tolerant: if the sentinel isn't found (e.g. someone substituted the
# vanilla upstream binary), the file is left untouched and we move on.
patch_host() {
  local path="$1"
  if [[ "${BUILDS_SKIP_HOST_PATCH:-0}" == "1" ]]; then return 0; fi
  if [[ ! -s "${path}" ]]; then return 0; fi
  python3 - "${path}" "${HOST}" <<'PY'
import pathlib, struct, sys

SENTINEL = b'__DBMP_HOST_SENTINEL_v1\x00'
SLOT_BYTES = 228

target = pathlib.Path(sys.argv[1])
host = sys.argv[2].encode('utf-8')
if len(host) > SLOT_BYTES:
    raise SystemExit(f'host too long ({len(host)} > {SLOT_BYTES}): {sys.argv[2]}')

data = bytearray(target.read_bytes())
hits = 0
start = 0
while True:
    idx = data.find(SENTINEL, start)
    if idx < 0:
        break
    hits += 1
    data[idx + 24:idx + 28] = struct.pack('<I', len(host))
    data[idx + 28:idx + 28 + SLOT_BYTES] = host + b'\x00' * (SLOT_BYTES - len(host))
    start = idx + 256

if hits == 0:
    print(f'[fetch_builds] WARN no DBMP host sentinel in {target.name} — '
          'serving as-is (binary may be vanilla or built from older patches)',
          file=sys.stderr)
else:
    target.write_bytes(bytes(data))
    print(f'[fetch_builds] stamped {target.name} -> {sys.argv[2]} ({hits} site{"s" if hits != 1 else ""})')
PY
}

fetch "${SERVER_LIN_URL}" "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64" || true
fetch "${SERVER_WIN_URL}" "${BUILDS_DIR}/BeamMP-Server.exe"               || true
fetch "${LAUNCHER_URL}"   "${BUILDS_DIR}/BeamMP-Launcher.exe"             || true
fetch "${CLIENT_URL}"     "${BUILDS_DIR}/BeamMP.zip"                      || true

patch_host "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64"
patch_host "${BUILDS_DIR}/BeamMP-Server.exe"
patch_host "${BUILDS_DIR}/BeamMP-Launcher.exe"

if [[ -s "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64" ]]; then
  chmod +x "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64"
fi

echo "[fetch_builds] done (host=${HOST:-<unpatched>})"
