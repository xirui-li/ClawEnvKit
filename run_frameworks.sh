#!/bin/bash
# Deprecated: renamed to run_harnesses.sh.
# This shim exists so existing automation / muscle memory keeps working.
# Use `bash run_harnesses.sh` going forward.

echo "[deprecated] run_frameworks.sh -> run_harnesses.sh (forwarding)" >&2
exec bash "$(dirname "$0")/run_harnesses.sh" "$@"
