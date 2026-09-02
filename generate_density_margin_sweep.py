#!/usr/bin/env python3
"""Generate terrain-only wheel-bed cases spanning compression-release margins."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_shared_wheel_screen import find_smooth_manifest, prepare_manifest


def margin_label(value: float) -> str:
    return f"{value:g}".replace("-", "neg").replace(".", "p")


def generate_sweep(
    queue_path: Path,
    output_dir: Path,
    margins: list[float],
    random_seed: int = 77,
) -> Path:
    if not margins:
        raise ValueError("At least one release margin is required")
    if any(value < 0 for value in margins):
        raise ValueError("Release margins must be nonnegative")
    if len(set(margins)) != len(margins):
        raise ValueError("Release margins must be unique")

    _, source_case = find_smooth_manifest(queue_path)
    terrain = source_case["terrain"]
    target_density = float(terrain["target_bulk_density_kg_m3"])
    particle_density = float(terrain["particle_density_kg_m3"])
    requested_density = target_density * (1.0 + max(margins))
    if requested_density >= particle_density:
        maximum = particle_density / target_density - 1.0
        raise ValueError(
            "Release margin requests a compressed bulk density at or above the "
            f"particle material density; margin must be below {maximum:.6g}"
        )

    project_root = queue_path.parents[2]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for margin in margins:
        label = margin_label(margin)
        destination = output_dir / f"shared-bed-margin-{label}.json"
        prepare_manifest(queue_path, destination, margin, random_seed)
        case = json.loads(destination.read_text())
        case["case_id"] += f"-margin{label}"
        case["model_status"] = "density_preparation_margin_sweep"
        case["purpose"] = (
            "Terrain-only compression-release sweep to identify a reproducible "
            "post-release bulk density near the physical simulant target."
        )
        case["density_margin_sweep"] = {
            "compression_release_margin": margin,
            "random_seed": random_seed,
        }
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    queue_output = output_dir / "density_margin_sweep_queue.json"
    queue_output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "run_policy": (
                    "Run terrain stage only with one fixed seed. Select the margin "
                    "with minimum absolute post-release density error, then repeat "
                    "the selected setting across additional seeds before wheel use."
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
    parser.add_argument("--margins", default="0.18,0.35,0.42,0.55")
    parser.add_argument("--random-seed", type=int, default=77)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    margins = [float(item.strip()) for item in args.margins.split(",") if item.strip()]
    queue = generate_sweep(
        args.queue.resolve(), args.output_dir.resolve(), margins, args.random_seed
    )
    print(f"Density-margin queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
