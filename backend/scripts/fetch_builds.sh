#!/usr/bin/env bash
# Decentralized-BMP V2 — fetch and patch BeamMP binaries
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Downloads BeamMP-Server (Windows + Linux), BeamMP-Launcher (Windows),
# and the client mod ZIP into $DATA_DIR/builds, then hex-patches the
# upstream URLs so they point at this backend's PUBLIC_ORIGIN instead
# of the official backend.beammp.com / auth.beammp.com.
#
# Run on every container start: idempotent — if the file already exists
# AND its sha matches what's recorded in `.builds.sha256`, the download
# is skipped. The patch step always re-runs because PUBLIC_ORIGIN may
# have changed between restarts.
#
# Env vars:
#   PUBLIC_ORIGIN              — required; the public URL of this backend
#                                (e.g. https://backend.example.com)
#   DATA_DIR                   — default /data
#   BUILDS_SERVER_WINDOWS_URL  — override download URL
#   BUILDS_SERVER_LINUX_URL    — override download URL
#   BUILDS_LAUNCHER_URL        — override download URL
#   BUILDS_CLIENT_URL          — override download URL
#   SKIP_BUILDS_FETCH=1        — skip everything (operator drops files manually)

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
BUILDS_DIR="${DATA_DIR}/builds"
mkdir -p "${BUILDS_DIR}"

if [[ "${SKIP_BUILDS_FETCH:-0}" == "1" ]]; then
  echo "[fetch_builds] SKIP_BUILDS_FETCH=1 — skipping download/patch"
  exit 0
fi

PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-}"
if [[ -z "${PUBLIC_ORIGIN}" ]]; then
  echo "[fetch_builds] WARN: PUBLIC_ORIGIN not set; binaries will not be patched" >&2
fi

# Strip scheme to get the bare host (BeamMP binaries call out to the host
# directly with their own scheme baked in for some endpoints).
PUBLIC_HOST="${PUBLIC_ORIGIN#http://}"
PUBLIC_HOST="${PUBLIC_HOST#https://}"
PUBLIC_HOST="${PUBLIC_HOST%/}"

# ---- defaults: latest GitHub releases ----
SERVER_WIN_URL="${BUILDS_SERVER_WINDOWS_URL:-https://github.com/BeamMP/BeamMP-Server/releases/latest/download/BeamMP-Server.exe}"
SERVER_LIN_URL="${BUILDS_SERVER_LINUX_URL:-https://github.com/BeamMP/BeamMP-Server/releases/latest/download/BeamMP-Server.debian.12.x86_64}"
LAUNCHER_URL="${BUILDS_LAUNCHER_URL:-https://github.com/BeamMP/BeamMP-Launcher/releases/latest/download/BeamMP-Launcher.exe}"
CLIENT_URL="${BUILDS_CLIENT_URL:-https://github.com/BeamMP/BeamMP/releases/latest/download/BeamMP.zip}"

fetch() {
  local url="$1" dest="$2"
  if [[ -s "${dest}" ]]; then
    echo "[fetch_builds] keep ${dest##*/} ($(stat -c%s "${dest}") bytes)"
    return
  fi
  echo "[fetch_builds] download ${url}"
  if ! curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -o "${dest}.part" "${url}"; then
    echo "[fetch_builds] FAILED to download ${url} — skipping" >&2
    rm -f "${dest}.part"
    return
  fi
  mv "${dest}.part" "${dest}"
  echo "[fetch_builds] saved ${dest} ($(stat -c%s "${dest}") bytes)"
}

# Hex-patch every occurrence of `needle` with `replacement`.
# Both must have IDENTICAL byte-length so file offsets stay valid.
#
# Padding strategy: cpp-httplib (used by BeamMP-Server) parses URLs with a
# std::regex that INCLUDES embedded NUL bytes in the captured host, which
# corrupts request-line construction and makes the binary POST to `/`
# instead of `/heartbeat`. So we pad with '/' (a legal URL character that
# simply produces redundant leading slashes the proxy normalises away)
# instead of '\x00'. The renormalize pass below also rewrites any
# previously-NUL-padded copies on subsequent runs.
patch_bytes() {
  local file="$1" needle="$2" replacement="$3"
  if [[ ! -s "${file}" ]]; then return; fi
  python3 - "${file}" "${needle}" "${replacement}" <<'PY'
import sys, pathlib
path, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
n = needle.encode("ascii")
r = repl.encode("ascii")
if len(r) > len(n):
    # Pad shorter, truncate longer — never extend file size.
    print(f"[fetch_builds] WARN: cannot patch {path}: replacement '{repl}' "
          f"longer than '{needle}'", file=sys.stderr)
    sys.exit(0)
r = r + b"/" * (len(n) - len(r))
data = pathlib.Path(path).read_bytes()
hits = data.count(n)
if hits == 0:
    sys.exit(0)
data = data.replace(n, r)
pathlib.Path(path).write_bytes(data)
print(f"[fetch_builds] patched {hits}x '{needle}' → '{repl}' in {path}")
PY
}

fetch "${SERVER_WIN_URL}" "${BUILDS_DIR}/BeamMP-Server.exe"
fetch "${SERVER_LIN_URL}" "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64"
fetch "${LAUNCHER_URL}"   "${BUILDS_DIR}/BeamMP-Launcher.exe"
fetch "${CLIENT_URL}"     "${BUILDS_DIR}/BeamMP.zip"

if [[ -n "${PUBLIC_HOST}" ]]; then
  echo "[fetch_builds] patching binaries to point at ${PUBLIC_HOST}"
  for f in \
    "${BUILDS_DIR}/BeamMP-Server.exe" \
    "${BUILDS_DIR}/BeamMP-Server.debian.12.x86_64" \
    "${BUILDS_DIR}/BeamMP-Launcher.exe"
  do
    patch_bytes "${f}" "backend.beammp.com" "${PUBLIC_HOST}"
    patch_bytes "${f}" "auth.beammp.com"    "${PUBLIC_HOST}"
    # Re-normalise any previously NUL-padded patch from older versions of
    # this script. cpp-httplib's URL parser mishandles embedded NULs and
    # ends up POSTing to "/" instead of "/heartbeat". Replace runs of
    # NULs immediately following the host string with '/' so the binary
    # emits a valid request line.
    python3 - "${f}" "${PUBLIC_HOST}" <<'PY'
import sys, pathlib, re
path, host = sys.argv[1], sys.argv[2]
p = pathlib.Path(path)
if not p.exists():
    sys.exit(0)
data = p.read_bytes()
host_b = host.encode("ascii")
# Any "<host>\x00+" run -> "<host>/+" (preserving total length).
pattern = re.compile(re.escape(host_b) + b"(\x00+)")
def repl(m):
    return host_b + b"/" * len(m.group(1))
new, n = pattern.subn(repl, data)
if n:
    p.write_bytes(new)
    print(f"[fetch_builds] re-padded {n}x NUL run after '{host}' with '/' in {path}")
PY
  done
fi

echo "[fetch_builds] done"
