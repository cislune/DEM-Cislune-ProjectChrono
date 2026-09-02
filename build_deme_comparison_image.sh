#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASE_IMAGE=${BASE_IMAGE:-dem-simulation:latest}
DEME_VERSION=${DEME_VERSION:-2.3.3}
TARGET_IMAGE=${TARGET_IMAGE:-"dem-simulation:deme-${DEME_VERSION}"}
PYTHON=/root/miniconda3/envs/myenv/bin/python

docker image inspect "$BASE_IMAGE" >/dev/null
baseline_id=$(docker image inspect "$BASE_IMAGE" --format '{{.Id}}')

docker build \
    --build-arg "BASE_IMAGE=$BASE_IMAGE" \
    --build-arg "DEME_VERSION=$DEME_VERSION" \
    --tag "$TARGET_IMAGE" \
    --file "$ROOT/docker/Dockerfile.deme-version" \
    "$ROOT"

target_id=$(docker image inspect "$TARGET_IMAGE" --format '{{.Id}}')
installed_version=$(docker run --rm --entrypoint "$PYTHON" "$TARGET_IMAGE" \
    -c 'import importlib.metadata as m; print(m.version("deme"))')

printf 'baseline_image=%s\n' "$BASE_IMAGE"
printf 'baseline_id=%s\n' "$baseline_id"
printf 'target_image=%s\n' "$TARGET_IMAGE"
printf 'target_id=%s\n' "$target_id"
printf 'deme_version=%s\n' "$installed_version"

if [[ $installed_version != "$DEME_VERSION" ]]; then
    echo "DEME version verification failed" >&2
    exit 1
fi
if [[ $baseline_id == "$target_id" ]]; then
    echo "comparison image unexpectedly matches baseline image" >&2
    exit 1
fi
