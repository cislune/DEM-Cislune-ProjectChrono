#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${GRASP_DEM_IMAGE:-dem-simulation:latest}
OUTPUT_ROOT=${GRASP_DEM_OUTPUT_ROOT:-"$HOME/grasp-dem-runs"}
CACHE_ROOT=${GRASP_DEM_CACHE_ROOT:-"$HOME/grasp-dem-cache"}
MAX_WALL_S=${GRASP_DEM_MAX_WALL_S:-}
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
cidfile="$OUTPUT_ROOT/_logs/${timestamp}_${case_id}_${stage}.cid"
started_epoch=$(date +%s)
started_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'run_started_utc=%s\n' "$started_iso" | tee "$log_path"

if [[ -n $MAX_WALL_S && ( ! $MAX_WALL_S =~ ^[1-9][0-9]*$ ) ]]; then
    echo "GRASP_DEM_MAX_WALL_S must be a positive integer" >&2
    exit 64
fi

cleanup_container() {
    if [[ -s $cidfile ]]; then
        docker stop -t 5 "$(cat "$cidfile")" >/dev/null 2>&1 || true
    fi
    rm -f "$cidfile"
}
trap cleanup_container INT TERM EXIT

set +e
docker_command=(docker run --rm --cidfile "$cidfile" --gpus all \
    -e CUDA_HOME="$CUDA_HOME_IN_CONTAINER" \
    -e GRASP_DEM_CONTAINER_DIGEST="$digest" \
    -v "$ROOT:/workspace:ro" \
    -v "$OUTPUT_ROOT:/outputs" \
    -v "$CACHE_ROOT:/root/.nv/ComputeCache" \
    -w /workspace \
    "$IMAGE" \
    "$PYTHON_IN_CONTAINER" -u /workspace/dem_case_runner.py "/workspace/$manifest_rel" \
    --output-root /outputs "$@")
if [[ -n $MAX_WALL_S ]]; then
    printf 'max_wall_s=%s\n' "$MAX_WALL_S" | tee -a "$log_path"
    timeout --signal=TERM --kill-after=10 "$MAX_WALL_S" "${docker_command[@]}" \
        2>&1 | tee -a "$log_path"
else
    "${docker_command[@]}" 2>&1 | tee -a "$log_path"
fi
status=${PIPESTATUS[0]}
set -e
cleanup_container
trap - INT TERM EXIT

finished_epoch=$(date +%s)
finished_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '\ncontainer_exit_status=%s\nrun_finished_utc=%s\nwall_duration_s=%s\n' \
    "$status" "$finished_iso" "$((finished_epoch - started_epoch))" >> "$log_path"

docker run --rm -v "$OUTPUT_ROOT:/outputs" "$IMAGE" \
    chown -R "$(id -u):$(id -g)" /outputs
docker run --rm -v "$CACHE_ROOT:/cache" "$IMAGE" \
    chown -R "$(id -u):$(id -g)" /cache
exit "$status"
