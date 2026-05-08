#!/usr/bin/env bash
# Decentralized-BMP V2 — patch BeamMP-Server source for configurable backend.
#
# Run from the root of a freshly checked-out BeamMP/BeamMP-Server source tree.
# Replaces the three hard-coded host getters in include/Common.h so the binary
# routes auth / heartbeat / socket.io to whatever host is set in the
# BMP_BACKEND_HOST env var at runtime, falling back to the official
# beammp.com hosts when the var is unset (preserves vanilla behaviour).
#
# This is the smallest possible source change — touches one file, no new
# headers, no CMakeLists changes. If upstream renames or moves these
# functions the script exits non-zero and CI fails loudly.

set -euo pipefail

target="include/Common.h"

if [[ ! -f "${target}" ]]; then
  echo "::error::Common.h not found at ${target} — upstream layout changed?" >&2
  exit 1
fi

# Python edits are easier to verify than sed for multi-line replacements and
# we get a real exit code if the markers we're looking for vanish.
python3 - "${target}" <<'PY'
import pathlib, re, sys

p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")
orig = src

# Helper expression embedded once, reused by the three replaced getters.
helper = (
    'std::string{ std::getenv("BMP_BACKEND_HOST") '
    '? std::getenv("BMP_BACKEND_HOST") '
    ': "{HOST}" }'
)

replacements = [
    # Pattern, replacement
    (
        re.compile(
            r'GetBackendUrlsInOrder\(\)\s*\{\s*'
            r'return\s*\{\s*'
            r'"backend\.beammp\.com"\s*,\s*'
            r'"backup1\.beammp\.com"\s*,\s*'
            r'"backup2\.beammp\.com"\s*\}\s*;\s*\}',
            re.DOTALL,
        ),
        'GetBackendUrlsInOrder() { return { ' + helper.replace("{HOST}", "backend.beammp.com") + ', "backup1.beammp.com", "backup2.beammp.com" }; }',
    ),
    (
        re.compile(
            r'GetBackendUrlForAuth\(\)\s*\{\s*'
            r'return\s*"auth\.beammp\.com"\s*;\s*\}'
        ),
        'GetBackendUrlForAuth() { return ' + helper.replace("{HOST}", "auth.beammp.com") + '; }',
    ),
    (
        re.compile(
            r'GetBackendUrlForSocketIO\(\)\s*\{\s*'
            r'return\s*"https://backend\.beammp\.com"\s*;\s*\}'
        ),
        'GetBackendUrlForSocketIO() { return std::string{"https://"} + ' + helper.replace("{HOST}", "backend.beammp.com") + '; }',
    ),
]

# Make sure <cstdlib> is available for std::getenv. Most TUs already get it
# transitively but include it explicitly to be safe.
if "#include <cstdlib>" not in src:
    src = src.replace("#pragma once", "#pragma once\n#include <cstdlib>", 1)

failures = []
for pat, repl in replacements:
    new, n = pat.subn(repl, src)
    if n == 0:
        failures.append(pat.pattern[:80])
    elif n > 1:
        failures.append(f"multiple matches for {pat.pattern[:80]}")
    src = new

if failures:
    sys.stderr.write("Patch FAILED — markers not found or ambiguous:\n")
    for f in failures:
        sys.stderr.write(f"  - {f}\n")
    sys.exit(2)

if src == orig:
    sys.stderr.write("Patch produced no changes — already patched?\n")
    sys.exit(3)

p.write_text(src, encoding="utf-8")
print(f"[patch] rewrote {p} ({len(orig)} -> {len(src)} bytes)")
PY

echo "[patch] BeamMP-Server source patched OK"
