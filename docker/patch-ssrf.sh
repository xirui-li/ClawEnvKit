#!/bin/bash
# Patch OpenClaw's SSRF check to allow private network access
# Used only for evaluation containers where mock services run on localhost
#
# This patches the built JS output (dist/), not the TypeScript source

set -e

OPENCLAW_DIR="${1:-/app}"

# Find the compiled SSRF module
SSRF_FILE=$(find "$OPENCLAW_DIR" -name "ssrf.js" -path "*/net/*" | head -1)

if [ -z "$SSRF_FILE" ]; then
    echo "WARNING: ssrf.js not found, skipping patch" >&2
    exit 0
fi

echo "Patching SSRF: $SSRF_FILE" >&2

# Replace the isPrivateNetworkAllowedByPolicy function to always return true
# when CLAWHARNESS_ALLOW_PRIVATE=1 is set
sed -i 's/function isPrivateNetworkAllowedByPolicy(policy) {/function isPrivateNetworkAllowedByPolicy(policy) { if (process.env.CLAWHARNESS_ALLOW_PRIVATE === "1") return true;/' "$SSRF_FILE"

echo "SSRF patched successfully" >&2
