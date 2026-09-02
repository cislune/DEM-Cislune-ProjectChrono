#!/usr/bin/env python3
"""Generate a bounded Alabama-wheel interface-friction calibration sweep."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file


DEFAULT_BED_CASE_ID = (
    "wheel-shared-bed-r8mm-cpt-informed-process-dt5us-margin0p18"
)
DEFAULT_BED_PREPARATION_SHA256 = (
    "eb71c681ff03e40ea76d2fc7e4286453f76aa6eaaf07f5e28004d98f9d6a3050"
)
DEFAULT_BED_TARGET_DENSITY_KG_M3 = 1703.2107925580497
DEFAULT_BED_ACHIEVED_DENSITY_KG_M3 = 1370.9852956027285


def friction_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def generate(
    alabama_path: Path,
    process_profile_path: Path,
    reference_path: Path,
    output_dir: Path,
    friction_values: list[float],
    bed_case_id: str = DEFAULT_BED_CASE_ID,
    bed_state_sha256: str | None = None,
    bed_preparation_sha256: str = DEFAULT_BED_PREPARATION_SHA256,
    bed_target_density_kg_m3: float = DEFAULT_BED_TARGET_DENSITY_KG_M3,
    bed_achieved_density_kg_m3: float = DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
) -> Path:
    if not friction_values or any(value <= 0 for value in friction_values):
        raise ValueError("Wheel friction values must be positive")
    if len(set(friction_values)) != len(friction_values):
        raise ValueError("Wheel friction values must be unique")

    try:
        cases_root = next(parent for parent in alabama_path.parents if parent.name == "cases")
    except StopIteration as exc:
        raise ValueError("Alabama manifest must be stored below a cases directory") from exc
    project_root = cases_root.parent
    alabama = json.loads(alabama_path.read_text())
    profile = json.loads(process_profile_path.read_text())
    reference = json.loads(reference_path.read_text())
    calibration_laps = reference["laps"][:5]
    target_torque = sorted(
        float(lap["active_abs_torque_nm"]["median"]) for lap in calibration_laps
    )[len(calibration_laps) // 2]
    target_load_kg = sorted(
        float(lap["active_load_kg_reported"]["median"]) for lap in calibration_laps
    )[len(calibration_laps) // 2]
    target_slip = sorted(
        float(lap["derived_slip"]["median"]) for lap in calibration_laps
    )[len(calibration_laps) // 2]
    target_speed = sorted(
        float(lap["derived_carriage_speed_m_s"]["median"])
        for lap in calibration_laps
    )[len(calibration_laps) // 2]

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for friction in friction_values:
        case = copy.deepcopy(alabama)
        case["case_id"] = f"calibrate-alabama-wheel-friction-mu{friction_label(friction)}"
        case["model_status"] = "cpt_informed_wheel_interface_calibration_pilot"
        case["purpose"] = (
            "With CPT-selected soil parameters fixed, fit only wheel-soil friction "
            "against UCF Alabama RIDER laps 1-5 median torque. The 8 mm shared bed "
            "is a computational pilot and retains an explicit density-mismatch gate."
        )
        case["terrain"] = copy.deepcopy(profile["terrain"])
        case["terrain"]["initial_state_case_id"] = bed_case_id
        case["terrain"]["initial_state_filename"] = "settled_terrain_data.csv"
        case["terrain"]["wheel_friction"] = friction
        case["test"] = copy.deepcopy(profile["test"])
        case["test"].update(
            {
                "normal_load_n": target_load_kg * 9.80665,
                "linear_speed_m_s": target_speed,
                "slip_ratios": [target_slip],
                "duration_s": 1.2,
                "passes": 1,
            }
        )
        case["solver"] = copy.deepcopy(profile["solver"])
        case["output"] = copy.deepcopy(profile["output"])
        case["analysis"] = {
            "minimum_lane_particles": 5,
            "density_gate_affects_status": False,
        }
        case["shared_sample_preparation"] = {
            "source_preparation_path": (
                f"case:{bed_case_id}/terrain/terrain_preparation.json"
            ),
            "source_preparation_sha256": bed_preparation_sha256,
            "target_bulk_density_kg_m3": bed_target_density_kg_m3,
            "post_release_bulk_density_kg_m3": bed_achieved_density_kg_m3,
            "achieved_to_target_ratio": (
                bed_achieved_density_kg_m3 / bed_target_density_kg_m3
            ),
            "random_seed": 77,
        }
        case["calibration_target"] = {
            "source_reference": str(reference_path.relative_to(project_root)),
            "source_reference_sha256": sha256_file(reference_path),
            "split": "Alabama RIDER laps 1-5",
            "median_abs_torque_nm": target_torque,
            "median_active_load_kg_reported": target_load_kg,
            "median_slip": target_slip,
            "median_carriage_speed_m_s": target_speed,
            "wheel_friction": friction,
            "fit_parameters": ["terrain.wheel_friction"],
            "frozen_soil_parameters_from": alabama.get("cpt_calibration_provenance"),
            "shared_bed_case_id": bed_case_id,
            "shared_bed_state_sha256": bed_state_sha256,
            "qualification": (
                "The shared 8 mm bed is below the measured out-track bulk density. "
                "This sweep brackets wheel-interface response but cannot close absolute validation."
            ),
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    queue_path = output_dir / "alabama_friction_sweep_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "calibration_split": "Alabama RIDER laps 1-5",
                "held_out_split": "Alabama RIDER laps 6-10",
                "fitted_parameter": "terrain.wheel_friction",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--alabama",
        type=Path,
        default=Path("cases/wheel_screen_cpt/screen-alabama_physical-coarse-cpt-informed.json"),
    )
    parser.add_argument(
        "--process-profile",
        type=Path,
        default=Path(
            "cases/wheel_phase_screen_r8mm_dt5us_1p2s/"
            "process-smooth_control-r8mm-dt5us-phase1p2s.json"
        ),
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("physical_references/alabama_rider_2026-08-04.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/alabama_friction_sweep_r8mm")
    )
    parser.add_argument("--frictions", default="0.3,0.5,0.7,0.9")
    parser.add_argument("--bed-case-id", default=DEFAULT_BED_CASE_ID)
    parser.add_argument("--bed-state-sha256")
    parser.add_argument(
        "--bed-preparation-sha256", default=DEFAULT_BED_PREPARATION_SHA256
    )
    parser.add_argument(
        "--bed-target-density-kg-m3",
        type=float,
        default=DEFAULT_BED_TARGET_DENSITY_KG_M3,
    )
    parser.add_argument(
        "--bed-achieved-density-kg-m3",
        type=float,
        default=DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    values = [float(item.strip()) for item in args.frictions.split(",") if item.strip()]
    queue = generate(
        args.alabama.resolve(),
        args.process_profile.resolve(),
        args.reference.resolve(),
        args.output_dir.resolve(),
        values,
        args.bed_case_id,
        args.bed_state_sha256,
        args.bed_preparation_sha256,
        args.bed_target_density_kg_m3,
        args.bed_achieved_density_kg_m3,
    )
    print(f"Alabama friction sweep: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
