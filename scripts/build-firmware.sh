#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || realpath "$(dirname "$0")/..")"
WORKFLOW="${REPO_ROOT}/.github/workflows/build.yaml"

ENTRYPOINT="/usr/local/lib/esphome-entrypoint.py"
if [[ ! -f "$ENTRYPOINT" ]]; then
    ENTRYPOINT=$(mktemp /tmp/esphome-entrypoint.XXXXXX.py)
    trap "rm -f $ENTRYPOINT" EXIT
    curl -fsSL "https://raw.githubusercontent.com/esphome/build-action/refs/heads/main/entrypoint.py" \
        -o "$ENTRYPOINT"
fi

mapfile -t CONFIGS < <(yq '.jobs.build.strategy.matrix."yaml-file"[]' "$WORKFLOW")

OUTPUT="${1:-/output}"
mkdir -p "$OUTPUT"

for yaml in "${CONFIGS[@]}"; do
    stem="${yaml%.yaml}"
    echo "==> Building $stem"
    python3 "$ENTRYPOINT" --complete-manifest "$yaml"

    name=$(yq '.substitutions.name' "$yaml")
    build_dir=$(find . -maxdepth 1 -type d -name "${name}-*" | head -1)
    mkdir -p "${OUTPUT}/${stem}"
    cp -r "${build_dir}/." "${OUTPUT}/${stem}/"
    rm -rf "${build_dir}"
    yq -i '.new_install_prompt_erase = true' "${OUTPUT}/${stem}/manifest.json"

    echo "    -> ${OUTPUT}/${stem}/"
done
