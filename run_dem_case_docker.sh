#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${GRASP_DEM_IMAGE:-dem-simulation:latest}
OUTPUT_ROOT=${GRASP_DEM_OUTPUT_ROOT:-"$HOME/grasp-dem-runs"}
CACHE_ROOT=${GRASP_DEM_CACHE_ROOT:-"$HOME/grasp-dem-cache"}
CUDA_HOME_IN_CONTAINER=/root/miniconda3/envs/myenv/targets/x86_64-linux
PYTHON_IN_CONTAINER=/root/miniconda3/envs/myenv/bin/python

if [[ $# -lt 1 ]]; then
    echo "usage: $0 MANIFEST [dem_case_runner.py options]" >&2
    exit 64
fi

manifest=$1
shift
if [[ $manifest = /* ]]; then
    case "$manifest" in
        "$ROOT"/*) manifest_rel=${manifest#"$ROOT"/} ;;
        *) echo "manifest must be inside $ROOT" >&2; exit 64 ;;
    esac
else
    manifest_rel=$manifest
fi
if [[ ! -f "$ROOT/$manifest_rel" ]]; then
    echo "manifest not found: $ROOT/$manifest_rel" >&2
    exit 66
fi

mkdir -p "$OUTPUT_ROOT"
mkdir -p "$OUTPUT_ROOT/_logs"
mkdir -p "$CACHE_ROOT"
digest=$(docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)
if [[ -z $digest ]]; then
    digest=$(docker image inspect "$IMAGE" --format '{{.Id}}')
fi

stage=preflight
previous=
for argument in "$@"; do
    if [[ $previous == --stage ]]; then
        stage=$argument
        break
    fi
    previous=$argument
done
case_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["case_id"])' "$ROOT/$manifest_rel")
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
log_path="$OUTPUT_ROOT/_logs/${timestamp}_${case_id}_${stage}.log"

set +e
docker run --rm --gpus all \
    -e CUDA_HOME="$CUDA_HOME_IN_CONTAINER" \
    -e GRASP_DEM_CONTAINER_DIGEST="$digest" \
    -v "$ROOT:/workspace:ro" \
    -v "$OUTPUT_ROOT:/outputs" \
    -v "$CACHE_ROOT:/root/.nv/ComputeCache" \
    -w /workspace \
    "$IMAGE" \
    "$PYTHON_IN_CONTAINER" -u /workspace/dem_case_runner.py "/workspace/$manifest_rel" \
    --output-root /outputs "$@" 2>&1 | tee "$log_path"
status=${PIPESTATUS[0]}
set -e

printf '\ncontainer_exit_status=%s\n' "$status" >> "$log_path"

docker run --rm -v "$OUTPUT_ROOT:/outputs" "$IMAGE" \
    chown -R "$(id -u):$(id -g)" /outputs
docker run --rm -v "$CACHE_ROOT:/cache" "$IMAGE" \
    chown -R "$(id -u):$(id -g)" /cache
exit "$status"
