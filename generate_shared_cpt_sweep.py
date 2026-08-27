#!/usr/bin/env python3
"""Build one 2 mm density bed and fixed-realization imported material-sweep cases."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from cpt_reference import sha256_file


PREPARATION_KEYS = (
    "target_bulk_density_kg_m3",
    "target_settled_bed_height_m",
    "compression_frame_time_s",
    "compression_speed_m_s",
    "compression_release_speed_m_s",
    "compression_max_time_s",
    "compression_release_margin",
    "post_compression_relax_s",
)


def common_bed_case(template_path: Path, output_path: Path) -> Path:
    case = copy.deepcopy(json.loads(template_path.read_text()))
    case["case_id"] = "cpt-out-track-common-bed-r2mm"
    case["model_status"] = "density_matched_shared_sample_preparation"
    case["purpose"] = (
        "Prepare one reproducible 2 mm particle realization at the UCF out-track bulk-density "
        "target for a fixed-geometry material sensitivity sweep."
    )
    terrain = case["terrain"]
    terrain.update(
        {
            "name": "ucf-out-track-shared-r2mm-bed",
            "base_particle_radius_m": 0.002,
            "youngs_modulus_pa": 1e8,
            "particle_friction": 0.05,
            "rolling_resistance": 0.0,
            "cohesion": 0.0,
            "time_step_s": 5e-6,
            "calibration_status": "low-friction shared sample preparation only",
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    return output_path


def imported_sweep(
    queue_path: Path,
    source_state: Path,
    output_dir: Path,
    runtime_source_state: Path | None = None,
) -> Path:
    queue = json.loads(queue_path.read_text())
    project_root = queue_path.parents[2]
    source_preparation_path = source_state.parent.parent / "terrain_preparation.json"
    if not source_preparation_path.is_file():
        raise FileNotFoundError(
            f"Shared bed preparation record is missing: {source_preparation_path}"
        )
    source_preparation = json.loads(source_preparation_path.read_text())
    target_density = source_preparation.get("target_bulk_density_kg_m3")
    achieved_density = source_preparation.get("post_release_bulk_density_kg_m3")
    if target_density is None or achieved_density is None:
        raise ValueError("Shared bed preparation record lacks target or achieved bulk density")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for value in queue["manifests"]:
        source_manifest = Path(value)
        if not source_manifest.is_absolute():
            source_manifest = project_root / source_manifest
        case = copy.deepcopy(json.loads(source_manifest.read_text()))
        case["case_id"] += "-shared-bed"
        case["model_status"] = "fixed_realization_material_sweep"
        terrain = case["terrain"]
        for key in PREPARATION_KEYS:
            terrain.pop(key, None)
        terrain.update(
            {
                "initial_state_csv": str(runtime_source_state or source_state.resolve()),
                "pre_penetration_relax_s": 0.05,
                "calibration_status": "material sweep on common measured-density realization",
            }
        )
        case["shared_sample_preparation"] = {
            "source_state": str(runtime_source_state or source_state.resolve()),
            "source_state_generation_path": str(source_state.resolve()),
            "source_state_sha256": sha256_file(source_state),
            "source_preparation": str(source_preparation_path.resolve()),
            "source_preparation_sha256": sha256_file(source_preparation_path),
            "target_bulk_density_kg_m3": target_density,
            "post_release_bulk_density_kg_m3": achieved_density,
            "achieved_to_target_ratio": float(achieved_density) / float(target_density),
            "interpretation": (
                "Particle positions are held constant across the sweep. Each material case receives "
                "a short gravity relaxation before penetration."
            ),
        }
        path = output_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(path)
    output_queue = output_dir / "cpt_shared_bed_queue.json"
    output_queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [str(path.relative_to(project_root)) for path in manifests],
                "run_policy": "Run stiffness brackets 1 5 and 9 first; rank before continuing six remaining cases.",
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
        "--template",
        type=Path,
        default=Path("cases/cpt_alabama_out_track_deme_bracket.json"),
    )
    parser.add_argument(
        "--common-bed-output",
        type=Path,
        default=Path("cases/cpt_shared/cpt-out-track-common-bed-r2mm.json"),
    )
    parser.add_argument("--source-state", type=Path)
    parser.add_argument(
        "--runtime-source-state",
        type=Path,
        help="Path to the same source state as visible inside the execution container",
    )
    parser.add_argument("--sweep-queue", type=Path, default=Path("cases/cpt_sweep/cpt_sweep_queue.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("cases/cpt_sweep_shared"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    common = common_bed_case(args.template.resolve(), args.common_bed_output.resolve())
    print(f"Common-bed case: {common}")
    if args.source_state:
        queue = imported_sweep(
            args.sweep_queue.resolve(),
            args.source_state.resolve(),
            args.output_dir.resolve(),
            args.runtime_source_state,
        )
        print(f"Imported sweep queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
