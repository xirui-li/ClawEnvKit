#!/bin/bash
# ── Build all harness images locally ─────────────────────────────────
#
# Builds Docker images with the locally-patched entrypoints (so the
# robustness fixes in docker/entrypoint_*.sh are baked in). Tags match
# what scripts/evaluate.py expects: clawenvkit:<harness>.
#
# Usage:
#   bash build_harnesses.sh                          # build all (skip ironclaw)
#   bash build_harnesses.sh --harness openclaw       # one harness only
#   bash build_harnesses.sh --include-ironclaw       # include ironclaw (needs local base)
#   bash build_harnesses.sh --no-cache               # rebuild from scratch
#
# Notes:
#   - claudecode builds standalone (FROM node:22-slim)
#   - Other harnesses pull base images from ghcr.io/xirui-li/clawenvkit-base-*
#   - ironclaw's base (ironclaw:latest) is upstream-only and must be built
#     manually first; it is skipped by default.
#
set -e

ALL_HARNESSES=(
    openclaw
    claudecode
    nanoclaw
    picoclaw
    zeroclaw
    copaw
    nemoclaw
    hermes
)

SELECTED=""
INCLUDE_IRONCLAW=false
# Harness base images on GHCR are linux/amd64-only. Force the platform so
# Apple Silicon (arm64) hosts pull the right manifest and run via Rosetta.
EXTRA_ARGS=("--platform=linux/amd64")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --harness) SELECTED="$2"; shift 2 ;;
        --include-ironclaw) INCLUDE_IRONCLAW=true; shift ;;
        --no-cache) EXTRA_ARGS+=("--no-cache"); shift ;;
        -h|--help)
            sed -n '2,18p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

if [[ -n "$SELECTED" ]]; then
    HARNESSES=("$SELECTED")
else
    HARNESSES=("${ALL_HARNESSES[@]}")
    [[ "$INCLUDE_IRONCLAW" == true ]] && HARNESSES+=("ironclaw")
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

echo "================================================"
echo "  Building harness images"
echo "  Targets: ${#HARNESSES[@]} (${HARNESSES[*]})"
echo "  Extra:   ${EXTRA_ARGS[*]:-(none)}"
echo "================================================"
echo ""

declare -a OK FAILED
START=$(date +%s)

for harness in "${HARNESSES[@]}"; do
    dockerfile="docker/Dockerfile.${harness}"
    tag="clawenvkit:${harness}"

    if [[ ! -f "$dockerfile" ]]; then
        echo "[skip] $harness — $dockerfile not found"
        FAILED+=("$harness (missing Dockerfile)")
        continue
    fi

    echo "━━━ build $harness → $tag ━━━"
    t0=$(date +%s)
    if docker build -f "$dockerfile" -t "$tag" "${EXTRA_ARGS[@]}" . ; then
        elapsed=$(( $(date +%s) - t0 ))
        echo "[ok] $harness built in ${elapsed}s"
        OK+=("$harness")
    else
        echo "[FAIL] $harness build failed"
        FAILED+=("$harness")
    fi
    echo ""
done

TOTAL=$(( $(date +%s) - START ))
echo "================================================"
echo "  Build summary  (total: ${TOTAL}s)"
echo "  ✓ ${#OK[@]} succeeded:  ${OK[*]:-(none)}"
echo "  ✗ ${#FAILED[@]} failed:    ${FAILED[*]:-(none)}"
echo "================================================"

[[ ${#FAILED[@]} -eq 0 ]]
