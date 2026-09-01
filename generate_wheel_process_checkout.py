#!/usr/bin/env python3
"""Generate a bounded wheel DEM process checkout before higher-fidelity runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CANDIDATE_SEQUENCE = ("smooth_control", "broad_wave_12")


def label_micrometers(value_m: float) -> str:
    return f"{value_m * 1_000_000:g}".replace(".", "p")


def label_millimeters(value_m: float) -> str:
    return f"{value_m * 1000:g}".replace(".", "p")


def build_case(candidate: dict, particle_radius_m: float, time_step_s: float) -> dict:
    dem = candidate["dem"]
    feature_height = float(candidate["design"]["feature_height_m"])
    radius_label = label_millimeters(particle_radius_m)
    step_label = label_micrometers(time_step_s)
    return {
        "schema_version": 1,
        "case_id": f"process-{candidate['name']}-r{radius_label}mm-dt{step_label}us",
        "model_status": "software_process_checkout",
        "purpose": (
            "Bounded checkout of terrain preparation, wheel OBJ import, prescribed motion, "
            "contact output, compaction analysis, and ranking. Runtime and integrity are the "
            "acceptance criteria; results are not physically interpreted."
        ),
        "wheel": {
            "obj": dem["obj"],
            "obj_units": "m",
            "source_axes": {"travel": "+x", "axle": "+y", "up": "+z"},
            "rolling_radius_m": dem["rolling_radius_m"],
            "envelope_radius_m": dem["envelope_radius_m"],
            "width_m": dem["width_m"],
            "effective_mass_kg": 10.0,
            "dimension_tolerance_fraction": 0.01,
            "feature_height_m": feature_height,
            "feature_height_in_particle_radii": (
                feature_height / particle_radius_m if feature_height else None
            ),
        },
        "test": {
            "gravity_m_s2": 9.81,
            "normal_load_n": 98.1,
            "linear_speed_m_s": 0.1,
            "kinematics_mode": "fixed_linear_speed",
            "slip_ratios": [0.09396784087753285],
            "duration_s": 0.08,
            "passes": 1,
        },
        "terrain": {
            "name": "bounded-cpt-informed-process-checkout",
            "calibration_status": (
                "CPT-selected material parameters transferred to a deliberately coarse "
                "runtime checkout; no absolute prediction permitted"
            ),
            "base_particle_radius_m": particle_radius_m,
            "particle_density_kg_m3": 2750.0,
            "youngs_modulus_pa": 300000000.0,
            "poissons_ratio": 0.3,
            "coefficient_of_restitution": 0.3,
            "particle_friction": 0.5,
            "rolling_resistance": 0.1,
            "cohesion": 0.0,
            "wheel_friction": 0.6,
            "wheel_restitution": 0.2,
            "wheel_cohesion": 0.0,
            "time_step_s": time_step_s,
            "bin_travel_length_m": 0.52,
            "bin_width_m": 0.20,
            "bed_depth_m": 0.105,
            "initial_fill_height_m": 0.085,
            "initial_solid_fraction": 0.55,
            "target_settled_bed_height_m": 0.075,
            "target_bulk_density_kg_m3": 1703.2107925580497,
            "settle_time_s": 0.05,
            "compression_frame_time_s": 0.0005,
            "compression_speed_m_s": 0.1,
            "compression_max_time_s": 0.5,
            "compression_release_margin": 0.18,
            "post_compression_relax_s": 0.05,
            "random_seed": 77,
        },
        "solver": {
            "max_velocity_m_s": 20.0,
            "error_out_velocity_m_s": 30.0,
            "max_triangles_in_bin": 100000,
            "error_out_avg_contacts": 500.0,
        },
        "output": {
            "terrain_frame_time_s": 0.0005,
            "terrain_progress_every_n_frames": 10,
            "terrain_write_every_n_frames": 100,
            "write_terrain_settling_motion": False,
            "wheel_frame_time_s": 0.001,
            "wheel_progress_every_n_frames": 10,
            "wheel_write_every_n_frames": 10,
            "write_wheel_terrain_motion": False,
            "write_wheel_mesh_motion": True,
            "write_contact_forces": True,
        },
        "physical_reference": {
            "reference_json": "physical_references/alabama_rider_2026-08-04.json",
            "comparison_condition": (
                "Kinematics and load follow the UCF RIDER Alabama reference, but this "
                "coarse checkout is not compared quantitatively with physical data"
            ),
        },
    }


def generate(
    catalog_path: Path,
    output_dir: Path,
    particle_radius_m: float,
    time_step_s: float,
) -> list[Path]:
    catalog = json.loads(catalog_path.read_text())
    candidates = {item["name"]: item for item in catalog["candidates"]}
    missing = [name for name in CANDIDATE_SEQUENCE if name not in candidates]
    if missing:
        raise ValueError(f"Candidate catalog is missing: {', '.join(missing)}")

    project_root = catalog_path.parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in CANDIDATE_SEQUENCE:
        case = build_case(candidates[name], particle_radius_m, time_step_s)
        path = output_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        paths.append(path)

    queue = {
        "schema_version": 1,
        "catalog": str(catalog_path.relative_to(project_root)),
        "manifests": [str(path.relative_to(project_root)) for path in paths],
        "sequence": list(CANDIDATE_SEQUENCE),
        "run_policy": (
            "Generate one shared bed, require a passing smooth-control pipeline, then run "
            "the broad-wave candidate. Increase fidelity only after bounded runtime and "
            "output-integrity gates pass."
        ),
    }
    queue_path = output_dir / "process_checkout_queue.json"
    queue_path.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog", type=Path, default=Path("wheel_candidates/candidate_catalog.json")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/wheel_process_checkout")
    )
    parser.add_argument("--particle-radius-m", type=float, default=0.012)
    parser.add_argument("--time-step-s", type=float, default=0.00001)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = generate(
        args.catalog.resolve(),
        args.output_dir.resolve(),
        args.particle_radius_m,
        args.time_step_s,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
