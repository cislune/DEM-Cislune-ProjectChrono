#!/usr/bin/env python3
"""Prepare one wheel-scale DEM bed and reuse it across comparative wheel cases."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file


def find_smooth_manifest(queue_path: Path) -> tuple[Path, dict]:
    queue = json.loads(queue_path.read_text())
    project_root = queue_path.parents[2]
    for value in queue["manifests"]:
        path = Path(value)
        if not path.is_absolute():
            path = project_root / path
        case = json.loads(path.read_text())
        if "smooth_control" in case["case_id"]:
            return path, case
    raise ValueError("CPT-informed queue does not contain a smooth-control case")


def prepare_manifest(
    queue_path: Path,
    output_path: Path,
    release_margin: float,
    random_seed: int = 77,
) -> Path:
    source_path, case = find_smooth_manifest(queue_path)
    case = copy.deepcopy(case)
    case["case_id"] = "wheel-shared-bed-r4mm-cpt-informed"
    case["model_status"] = "cpt_informed_shared_bed_preparation"
    case["purpose"] = (
        "Prepare one reproducible wheel-scale 4 mm bed for the accelerated comparative screen. "
        "No wheel result is interpreted from this terrain-only case."
    )
    case["terrain"].pop("initial_state_csv", None)
    case["terrain"]["compression_release_margin"] = release_margin
    case["terrain"]["random_seed"] = random_seed
    case["shared_bed_generation"] = {
        "source_manifest": str(source_path.resolve()),
        "source_manifest_sha256": sha256_file(source_path),
        "release_margin": release_margin,
        "random_seed": random_seed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    return output_path


def screen_queue(
    queue_path: Path,
    source_state: Path,
    runtime_source_state: Path | None,
    output_dir: Path,
) -> Path:
    queue = json.loads(queue_path.read_text())
    project_root = queue_path.parents[2]
    preparation_path = source_state.parent.parent / "terrain_preparation.json"
    if not preparation_path.is_file():
        raise FileNotFoundError(f"Wheel bed preparation record is missing: {preparation_path}")
    preparation = json.loads(preparation_path.read_text())
    target = preparation.get("target_bulk_density_kg_m3")
    achieved = preparation.get("post_release_bulk_density_kg_m3")
    if target is None or achieved is None:
        raise ValueError("Wheel bed preparation lacks target or achieved bulk density")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for value in queue["manifests"]:
        source = Path(value)
        if not source.is_absolute():
            source = project_root / source
        case = copy.deepcopy(json.loads(source.read_text()))
        case["case_id"] += "-shared-bed"
        case["model_status"] = "cpt_informed_fixed_realization_wheel_screen"
        case["terrain"]["initial_state_csv"] = str(
            runtime_source_state or source_state.resolve()
        )
        case["shared_sample_preparation"] = {
            "source_state": str(runtime_source_state or source_state.resolve()),
            "source_state_generation_path": str(source_state.resolve()),
            "source_state_sha256": sha256_file(source_state),
            "source_preparation_path": str(preparation_path.resolve()),
            "source_preparation_sha256": sha256_file(preparation_path),
            "target_bulk_density_kg_m3": target,
            "post_release_bulk_density_kg_m3": achieved,
            "achieved_to_target_ratio": float(achieved) / float(target),
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    output_queue = output_dir / "wheel_screen_shared_bed_queue.json"
    output_queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [str(path.relative_to(project_root)) for path in manifests],
                "run_policy": (
                    "Run Alabama, smooth control, broad wave, and low grouser first; "
                    "rank the compaction-mobility result before extending the queue."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return output_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("cases/wheel_screen_cpt/wheel_screen_cpt_informed_queue.json"),
    )
    parser.add_argument(
        "--shared-bed-manifest",
        type=Path,
        default=Path("cases/wheel_screen_shared/wheel-shared-bed-r4mm-cpt-informed.json"),
    )
    parser.add_argument("--release-margin", type=float, default=0.18)
    parser.add_argument("--random-seed", type=int, default=77)
    parser.add_argument("--source-state", type=Path)
    parser.add_argument("--runtime-source-state", type=Path)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/wheel_screen_shared")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepared = prepare_manifest(
        args.queue.resolve(),
        args.shared_bed_manifest.resolve(),
        args.release_margin,
        args.random_seed,
    )
    print(f"Shared wheel-bed manifest: {prepared}")
    if args.source_state:
        queue = screen_queue(
            args.queue.resolve(),
            args.source_state.resolve(),
            args.runtime_source_state,
            args.output_dir.resolve(),
        )
        print(f"Shared wheel-screen queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
