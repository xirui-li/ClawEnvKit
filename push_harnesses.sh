#!/bin/bash
# ── Tag & push locally-built harness images to GHCR ──────────────────
#
# Run AFTER `bash build_harnesses.sh` — this script tags the local
# clawenvkit:<harness> images for ghcr.io and pushes them so users
# of `docker pull ghcr.io/xirui-li/clawenvkit-<harness>:latest` get
# the patched entrypoints.
#
# Prerequisites (one-time):
#   1. Create a GitHub PAT with write:packages scope
#      https://github.com/settings/tokens
#   2. Log in to GHCR:
#      echo "$GHCR_TOKEN" | docker login ghcr.io -u xirui-li --password-stdin
#
# Usage:
#   bash push_harnesses.sh --version v0.4.0           # push :latest + :v0.4.0
#   bash push_harnesses.sh --version v0.4.0 --dry-run # show commands, don't run
#   bash push_harnesses.sh --version v0.4.0 --harness openclaw
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

GHCR_OWNER="xirui-li"
VERSION=""
SELECTED=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --harness) SELECTED="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --owner)   GHCR_OWNER="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,21p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "unknown arg: $1"; exit 1 ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    echo "ERROR: --version is required (e.g. --version v0.4.0)"
    exit 1
fi

if [[ -n "$SELECTED" ]]; then
    HARNESSES=("$SELECTED")
else
    HARNESSES=("${ALL_HARNESSES[@]}")
fi

run() {
    echo "+ $*"
    [[ "$DRY_RUN" == true ]] || "$@"
}

echo "================================================"
echo "  Push harness images to GHCR"
echo "  Owner:    $GHCR_OWNER"
echo "  Version:  $VERSION (and :latest)"
echo "  Targets:  ${#HARNESSES[@]} (${HARNESSES[*]})"
echo "  Dry run:  $DRY_RUN"
echo "================================================"
echo ""

# Sanity: confirm we're logged into ghcr (skip in dry-run)
if [[ "$DRY_RUN" != true ]]; then
    if ! docker info 2>/dev/null | grep -q "ghcr.io"; then
        # docker info doesn't always show registries; check creds file
        if ! grep -q "ghcr.io" ~/.docker/config.json 2>/dev/null; then
            echo "WARNING: no ghcr.io entry in ~/.docker/config.json — you may need to:"
            echo "  echo \$GHCR_TOKEN | docker login ghcr.io -u $GHCR_OWNER --password-stdin"
            read -p "Continue anyway? [y/N] " confirm
            [[ "$confirm" == "y" ]] || exit 1
        fi
    fi
fi

declare -a OK FAILED
for harness in "${HARNESSES[@]}"; do
    local_tag="clawenvkit:${harness}"
    remote_base="ghcr.io/${GHCR_OWNER}/clawenvkit-${harness}"

    # Verify local image exists
    if ! docker image inspect "$local_tag" >/dev/null 2>&1; then
        echo "[skip] $harness — local image $local_tag missing (run build_harnesses.sh first)"
        FAILED+=("$harness (no local image)")
        continue
    fi

    echo "━━━ push $harness ━━━"
    set +e
    run docker tag "$local_tag" "${remote_base}:${VERSION}"
    run docker tag "$local_tag" "${remote_base}:latest"
    run docker push "${remote_base}:${VERSION}"
    rc1=$?
    run docker push "${remote_base}:latest"
    rc2=$?
    set -e

    if [[ $rc1 -eq 0 && $rc2 -eq 0 ]]; then
        OK+=("$harness")
    else
        FAILED+=("$harness")
    fi
    echo ""
done

echo "================================================"
echo "  Push summary"
echo "  ✓ ${#OK[@]} succeeded:  ${OK[*]:-(none)}"
echo "  ✗ ${#FAILED[@]} failed:    ${FAILED[*]:-(none)}"
echo "================================================"

[[ ${#FAILED[@]} -eq 0 ]]
