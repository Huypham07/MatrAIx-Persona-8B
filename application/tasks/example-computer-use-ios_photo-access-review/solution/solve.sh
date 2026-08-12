#!/usr/bin/env bash
set -euo pipefail

# Oracle = artifact-contract smoke only (no LLM, no iOS UI).
# Proves output mounts + verifier accept a valid decision.json.
# For simulator / use.computer harness smoke, run one persona-computer-1 trial.

OUTPUT_DIR="${PLAYGROUND_OUTPUT_DIR:-${MATRIX_OUTPUT_DIR:-/app/output}}"
mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_DIR/decision.json" <<'EOF'
{
  "app_reviewed": "Photos",
  "photo_access_level": "selected_photos",
  "reason": "I only want this app to see the few images I choose on purpose instead of my full library."
}
EOF
