#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEME_VERSION=${DEME_VERSION:-2.3.3}
TARGET_IMAGE=${TARGET_IMAGE:-"dem-simulation:deme-${DEME_VERSION}"}
MANIFEST=${MANIFEST:-cases/solver_determinism_probe_mu1p05_lap03/determinism-probe-alabama-cub.json}
SEED_CASE=${SEED_CASE:?SEED_CASE must name the imported settled-terrain case directory}
OUTPUT_ROOT=${OUTPUT_ROOT:?OUTPUT_ROOT must name an isolated version-comparison directory}
CACHE_ROOT=${CACHE_ROOT:-"$OUTPUT_ROOT/_cache"}
REPEATS=${REPEATS:-3}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-6}
MAX_WALL_S=${MAX_WALL_S:-1200}
SILENCE_TIMEOUT_S=${SILENCE_TIMEOUT_S:-90}
PROFILE_ROOT="$OUTPUT_ROOT/deme-${DEME_VERSION}-cub"

mkdir -p "$OUTPUT_ROOT" "$CACHE_ROOT"

DEME_VERSION="$DEME_VERSION" TARGET_IMAGE="$TARGET_IMAGE" \
    "$ROOT/build_deme_comparison_image.sh" \
    | tee "$OUTPUT_ROOT/image-build-provenance.txt"

docker run --rm --gpus all --entrypoint /root/miniconda3/envs/myenv/bin/python \
    "$TARGET_IMAGE" \
    -c 'import DEME, importlib.metadata as m; print("DEME", m.version("deme")); print("CUDA probe ready")' \
    | tee "$OUTPUT_ROOT/cuda-import-probe.txt"

export GRASP_DEM_IMAGE="$TARGET_IMAGE"
export GRASP_DEM_SILENCE_TIMEOUT_S="$SILENCE_TIMEOUT_S"
python3 "$ROOT/run_exact_manifest_repeats.py" "$ROOT/$MANIFEST" \
    --seed-case "$SEED_CASE" \
    --output-root "$PROFILE_ROOT" \
    --cache-root "$CACHE_ROOT" \
    --repeats "$REPEATS" \
    --max-attempts "$MAX_ATTEMPTS" \
    --max-wall-s "$MAX_WALL_S" || true

python3 "$ROOT/diagnose_exact_repeat_divergence.py" "$PROFILE_ROOT" \
    --json "$PROFILE_ROOT/exact-repeat-divergence.json" || true
python3 "$ROOT/evaluate_solver_determinism_profiles.py" "$OUTPUT_ROOT" \
    --json "$OUTPUT_ROOT/profile-comparison.json" \
    --csv "$OUTPUT_ROOT/profile-comparison.csv"
