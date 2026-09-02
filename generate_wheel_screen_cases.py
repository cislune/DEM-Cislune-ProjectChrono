#!/usr/bin/env python3
"""Build identical comparative DEM manifests for the generated wheel family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_case(candidate: dict, particle_radius_m: float) -> dict:
    dem = candidate["dem"]
    estimated_feature = float(candidate["design"]["feature_height_m"])
    feature_resolution = estimated_feature / particle_radius_m if estimated_feature else None
    return {
        "schema_version": 1,
        "case_id": f"screen-{candidate['name']}-coarse",
        "model_status": "uncalibrated_relative_screen",
        "purpose": (
            "Comparative wheel-shape screen at identical load, slip, bed realization, and solver settings. "
            "Use to down-select shapes, not as an absolute compaction prediction."
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
            "feature_height_m": estimated_feature,
            "feature_height_in_particle_radii": feature_resolution,
        },
        "test": {
            "gravity_m_s2": 9.81,
            "normal_load_n": 98.1,
            "linear_speed_m_s": 0.1,
            "kinematics_mode": "fixed_linear_speed",
            "slip_ratios": [0.09396784087753285],
            "duration_s": 0.75,
            "passes": 1,
        },
        "terrain": {
            "name": "shared-coarse-relative-screen-bed",
            "calibration_status": "initial nominal values; replace with CPT-selected material set",
            "base_particle_radius_m": particle_radius_m,
            "particle_density_kg_m3": 2750.0,
            "youngs_modulus_pa": 1000000000.0,
            "poissons_ratio": 0.3,
            "coefficient_of_restitution": 0.3,
            "particle_friction": 0.4,
            "rolling_resistance": 0.02,
            "cohesion": 50.0,
            "wheel_friction": 0.6,
            "wheel_restitution": 0.2,
            "wheel_cohesion": 0.0,
            "time_step_s": 0.000005,
            "bin_travel_length_m": 0.60,
            "bin_width_m": 0.16,
            "bed_depth_m": 0.12,
            "initial_fill_height_m": 0.10,
            "initial_solid_fraction": 0.55,
            "target_settled_bed_height_m": 0.10,
            "target_bulk_density_kg_m3": 1703.2107925580497,
            "settle_time_s": 0.8,
            "compression_frame_time_s": 0.002,
            "compression_speed_m_s": 0.03,
            "compression_max_time_s": 12.0,
            "compression_release_margin": 0.0,
            "post_compression_relax_s": 0.2,
        },
        "solver": {
            "max_velocity_m_s": 20.0,
            "error_out_velocity_m_s": 30.0,
            "max_triangles_in_bin": 100000,
            "error_out_avg_contacts": 500.0,
        },
        "output": {
            "terrain_frame_time_s": 0.002,
            "terrain_write_every_n_frames": 100,
            "write_terrain_settling_motion": False,
            "wheel_frame_time_s": 0.002,
            "wheel_write_every_n_frames": 10,
            "write_wheel_terrain_motion": False,
            "write_wheel_mesh_motion": True,
            "write_contact_forces": True,
        },
        "physical_reference": {
            "reference_json": "physical_references/alabama_rider_2026-08-04.json",
            "comparison_condition": "UCF RIDER Alabama wheel 10 kg-equivalent, 0.1 m/s, approximately 9.4% median slip",
        },
    }


def generate(catalog_path: Path, output_dir: Path, particle_radius_m: float) -> list[Path]:
    catalog = json.loads(catalog_path.read_text())
    project_root = catalog_path.parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for candidate in catalog["candidates"]:
        case = build_case(candidate, particle_radius_m)
        path = output_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        paths.append(path)
    queue = {
        "schema_version": 1,
        "catalog": str(catalog_path.relative_to(project_root)),
        "manifests": [str(path.relative_to(project_root)) for path in paths],
        "sequence": [
            "smooth_control",
            "broad_wave_12",
            "low_grouser_16",
            "staggered_wave_12",
            "chevron_wave_14",
        ],
        "interpretation": "Run smooth first, then broad wave and low grouser; defer the final two if the first three establish a clear frontier.",
    }
    (output_dir / "screen_queue.json").write_text(
        json.dumps(queue, indent=2, sort_keys=True) + "\n"
    )
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog", type=Path, default=Path("wheel_candidates/candidate_catalog.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("cases/wheel_screen"))
    parser.add_argument("--particle-radius-m", type=float, default=0.004)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = generate(args.catalog.resolve(), args.output_dir.resolve(), args.particle_radius_m)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
