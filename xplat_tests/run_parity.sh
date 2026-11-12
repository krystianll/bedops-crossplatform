#!/usr/bin/env bash
# Dump the results of every parity case for one BEDOPS build (see README.md).
# usage: xplat_tests/run_parity.sh BIN_DIR OUT.json [WORK_DIR] [case-substring]
#   BIN_DIR   directory with the programs (bedops, bedmap, ..., unstarch[.exe])
#   OUT.json  where to write the dump; compare two dumps with
#             python3 xplat_tests/parity.py cmp A.json B.json
#   WORK_DIR  scratch directory (default: a new temporary one, removed after)
# The data are the tree's tests/ directory. PYTHON overrides the interpreter
# (default python3, else python).
set -eu
[ $# -ge 2 ] || { sed -n '2,9p' "$0"; exit 2; }
H=$(cd "$(dirname "$0")/.." && pwd)
BIN=$1 OUT=$2 W=${3:-} ONLY=${4:-}
PY=${PYTHON:-$(command -v python3 || command -v python)}
[ -d "$BIN" ] || { echo "not a directory: $BIN"; exit 2; }
if [ -z "$W" ]; then
	W=$(mktemp -d)
	trap 'rm -rf "$W"' EXIT
fi
"$PY" "$H/xplat_tests/parity.py" dump "$BIN" "$H/tests" "$W" "$OUT" ${ONLY:+"$ONLY"}
