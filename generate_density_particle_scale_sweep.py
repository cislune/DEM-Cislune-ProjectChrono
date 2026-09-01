#!/usr/bin/env python3
"""Generate terrain-only cases to measure density sensitivity to particle scale."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file
from generate_shared_wheel_screen import find_smooth_manifest


def label_mm(value_m: float) -> str:
    return f"{value_m * 1000:g}".replace(".", "p")


def label_us(value_s: float) -> str:
    return f"{value_s * 1_000_000:g}".replace(".", "p")


def generate_sweep(
    queue_path: Path,
    output_dir: Path,
    particle_radii_m: list[float],
    release_margin: float = 0.18,
    random_seed: int = 77,
) -> Path:
    if not particle_radii_m or any(value <= 0 for value in particle_radii_m):
        raise ValueError("Particle radii must be positive")
    if len(set(particle_radii_m)) != len(particle_radii_m):
        raise ValueError("Particle radii must be unique")

    source_path, source_case = find_smooth_manifest(queue_path)
    project_root = queue_path.parents[2].resolve()
    base_radius = float(source_case["terrain"]["base_particle_radius_m"])
    base_step = float(source_case["terrain"]["time_step_s"])
    target_density = float(source_case["terrain"]["target_bulk_density_kg_m3"])
    particle_density = float(source_case["terrain"]["particle_density_kg_m3"])
    if target_density * (1.0 + release_margin) >= particle_density:
        raise ValueError("Release margin requests an impossible compressed bulk density")
    try:
        source_reference = str(source_path.resolve().relative_to(project_root))
    except ValueError:
        source_reference = str(source_path.resolve())

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for radius in particle_radii_m:
        time_step = base_step * radius / base_radius
        radius_label = label_mm(radius)
        step_label = label_us(time_step)
        case = copy.deepcopy(source_case)
        case["case_id"] = (
            f"wheel-shared-bed-density-scale-r{radius_label}mm-dt{step_label}us"
        )
        case["model_status"] = "density_preparation_particle_scale_sweep"
        case["source_model_status"] = source_case.get("model_status")
        case["purpose"] = (
            "Terrain-only resolution sweep to quantify whether coarse spherical "
            "particles prevent the released bed from reaching simulant bulk density."
        )
        terrain = case["terrain"]
        terrain.pop("initial_state_csv", None)
        terrain["base_particle_radius_m"] = radius
        terrain["time_step_s"] = time_step
        terrain["compression_release_margin"] = release_margin
        terrain["random_seed"] = random_seed
        case["density_particle_scale_sweep"] = {
            "source_manifest": source_reference,
            "source_manifest_sha256": sha256_file(source_path),
            "base_particle_radius_m": radius,
            "time_step_s": time_step,
            "compression_release_margin": release_margin,
            "random_seed": random_seed,
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    queue_output = output_dir / "density_particle_scale_sweep_queue.json"
    queue_output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "run_policy": (
                    "Run terrain stage only. Begin with 6 mm; run 4 mm only if the "
                    "density trend justifies the added particle count."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--particle-radii-mm", default="8,6,4")
    parser.add_argument("--release-margin", type=float, default=0.18)
    parser.add_argument("--random-seed", type=int, default=77)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    radii = [
        float(item.strip()) / 1000.0
        for item in args.particle_radii_mm.split(",")
        if item.strip()
    ]
    queue = generate_sweep(
        args.queue.resolve(),
        args.output_dir.resolve(),
        radii,
        args.release_margin,
        args.random_seed,
    )
    print(f"Density particle-scale queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
