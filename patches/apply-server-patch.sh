#!/usr/bin/env bash
# Decentralized-BMP V2 — patch BeamMP-Server source for configurable backend.
#
# Run from the root of a freshly checked-out BeamMP/BeamMP-Server source tree.
# Adds a tiny helper header `include/_DBMP_BackendUrl.h` exposing
#
#   std::string dbmp::backend_url();   // "https://${BMP_BACKEND_HOST}" or "https://backend.beammp.com"
#   std::string dbmp::auth_url();      // "https://${BMP_BACKEND_HOST}" or "https://auth.beammp.com"
#
# then literal-replaces every occurrence of "https://backend.beammp.com"
# and "https://auth.beammp.com" in src/ and include/ with calls to those
# helpers. With BMP_BACKEND_HOST unset the binary behaves identically to
# the upstream release; with it set, all backend traffic is redirected.
#
# Why literal substitution instead of function-body regex: upstream
# refactors these getters between releases (added/removed backups,
# scheme moved into the literal, etc.). A literal-by-literal sweep is
# resilient against those rearrangements.

set -euo pipefail

if [[ ! -f "include/Common.h" ]]; then
  echo "::error::include/Common.h not found — upstream layout changed?" >&2
  exit 1
fi

# 1. Drop the helper header.
mkdir -p include
cat > include/_DBMP_BackendUrl.h <<'HEADER'
// SPDX-License-Identifier: AGPL-3.0-or-later
// Decentralized-BMP V2 — runtime-configurable backend URL helpers.
//
// Reads BMP_BACKEND_HOST at every call (cheap; fallback once cached).
// Two helpers because upstream traditionally split auth and main backend
// onto separate hosts — we redirect both to the same operator host.
#pragma once

#include <cstdlib>
#include <string>

namespace dbmp {

inline std::string _host(const char* fallback) {
    const char* env = std::getenv("BMP_BACKEND_HOST");
    if (env && env[0] != '\0') {
        return std::string("https://") + env;
    }
    return std::string("https://") + fallback;
}

inline std::string backend_url() { return _host("backend.beammp.com"); }
inline std::string auth_url()    { return _host("auth.beammp.com"); }

} // namespace dbmp
HEADER
echo "[patch] wrote include/_DBMP_BackendUrl.h"

# 2. Inject the include into Common.h (where most of the literals live).
python3 - <<'PY'
import pathlib, sys
p = pathlib.Path("include/Common.h")
src = p.read_text(encoding="utf-8")
needle = '#include "_DBMP_BackendUrl.h"'
if needle in src:
    print("[patch] Common.h already includes _DBMP_BackendUrl.h")
else:
    if "#pragma once" not in src:
        sys.stderr.write("::error::no #pragma once in Common.h\n")
        sys.exit(1)
    src = src.replace("#pragma once", '#pragma once\n' + needle, 1)
    p.write_text(src, encoding="utf-8")
    print("[patch] injected include into Common.h")
PY

# 3. Sweep the tree for the two literals and substitute. Limit to .cpp/.h/.hpp
#    under src/ and include/ to avoid touching docs/tests/CI YAML.
python3 - <<'PY'
import pathlib, sys

ROOTS = ["src", "include"]
LITERALS = {
    '"https://backend.beammp.com"': 'dbmp::backend_url()',
    '"https://auth.beammp.com"':    'dbmp::auth_url()',
}

total = 0
files_touched = 0
for root in ROOTS:
    for path in pathlib.Path(root).rglob("*"):
        if path.suffix.lower() not in (".cpp", ".h", ".hpp", ".cc", ".cxx"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        local = 0
        for needle, replacement in LITERALS.items():
            count = new.count(needle)
            if count:
                new = new.replace(needle, replacement)
                local += count
        if local:
            # The replacement uses dbmp:: helpers — make sure the header is
            # available in this TU. Common.h gets it directly; everything
            # else gets it via Common.h's transitive include in practice,
            # but inject defensively if the file doesn't include Common.h.
            if 'Common.h' not in new and '_DBMP_BackendUrl.h' not in new:
                # Insert after the first #include or at top.
                lines = new.splitlines(keepends=True)
                inserted = False
                for i, line in enumerate(lines):
                    if line.startswith("#include"):
                        lines.insert(i, '#include "_DBMP_BackendUrl.h"\n')
                        inserted = True
                        break
                if not inserted:
                    lines.insert(0, '#include "_DBMP_BackendUrl.h"\n')
                new = "".join(lines)
            path.write_text(new, encoding="utf-8")
            print(f"[patch] {path}: {local} literal(s) replaced")
            total += local
            files_touched += 1

if total == 0:
    sys.stderr.write("::error::no occurrences of \"https://backend.beammp.com\" or \"https://auth.beammp.com\" found — upstream changed shape?\n")
    sys.exit(2)
print(f"[patch] total: {total} substitution(s) across {files_touched} file(s)")
PY

# 4. Verify nothing slipped through.
remaining=$(grep -rE '"https://(backend|auth)\.beammp\.com"' src include 2>/dev/null || true)
if [[ -n "${remaining}" ]]; then
  echo "::error::leftover literals after patch:" >&2
  echo "${remaining}" >&2
  exit 4
fi

echo "[patch] BeamMP-Server source patched OK"
