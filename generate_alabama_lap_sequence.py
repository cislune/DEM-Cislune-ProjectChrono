#!/usr/bin/env python3
"""Generate a chained, lap-conditioned Alabama RIDER validation sequence."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file, slip_label
from generate_alabama_friction_sweep import (
    DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
    DEFAULT_BED_CASE_ID,
    DEFAULT_BED_PREPARATION_SHA256,
    DEFAULT_BED_TARGET_DENSITY_KG_M3,
    friction_label,
)


def final_state_relative_path(slip: float) -> str:
    label = slip_label(slip)
    return (
        f"wheel/slip_{label}/pass_01/Trial 1/Slip {label}/settled data/"
        f"slip_sinkage_settled_data_slip_{label}.csv"
    )


def generate(
    alabama_path: Path,
    process_profile_path: Path,
    reference_path: Path,
    output_dir: Path,
    wheel_friction: float,
    bed_case_id: str = DEFAULT_BED_CASE_ID,
    bed_state_sha256: str | None = None,
    bed_preparation_sha256: str = DEFAULT_BED_PREPARATION_SHA256,
    bed_target_density_kg_m3: float = DEFAULT_BED_TARGET_DENSITY_KG_M3,
    bed_achieved_density_kg_m3: float = DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
) -> Path:
    if wheel_friction <= 0:
        raise ValueError("Wheel friction must be positive")
    try:
        cases_root = next(parent for parent in alabama_path.parents if parent.name == "cases")
    except StopIteration as exc:
        raise ValueError("Alabama manifest must be stored below a cases directory") from exc
    project_root = cases_root.parent
    alabama = json.loads(alabama_path.read_text())
    profile = json.loads(process_profile_path.read_text())
    reference = json.loads(reference_path.read_text())
    laps = reference["laps"]
    if len(laps) != 10:
        raise ValueError(f"Expected 10 Alabama RIDER laps, found {len(laps)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[Path] = []
    previous_case_id: str | None = None
    previous_slip: float | None = None
    reference_sha256 = sha256_file(reference_path)
    for index, lap in enumerate(laps, 1):
        slip = float(lap["derived_slip"]["median"])
        speed = float(lap["derived_carriage_speed_m_s"]["median"])
        load_kg = float(lap["active_load_kg_reported"]["median"])
        split = "calibration" if index <= 5 else "held_out_validation"
        case = copy.deepcopy(alabama)
        case_id = (
            f"alabama-rider-sequence-mu{friction_label(wheel_friction)}-lap{index:02d}"
        )
        case["case_id"] = case_id
        case["model_status"] = "cpt_informed_rider_sequence_pilot"
        case["purpose"] = (
            f"Run a bounded coupon at the measured Alabama RIDER lap {index} load, speed, "
            f"and slip with wheel friction frozen at {wheel_friction:g}. Soil state is "
            "chained lap to lap so laps 6-10 remain held out from parameter selection."
        )
        case["terrain"] = copy.deepcopy(profile["terrain"])
        case["terrain"]["wheel_friction"] = wheel_friction
        if previous_case_id is None:
            case["terrain"]["initial_state_case_id"] = bed_case_id
            case["terrain"]["initial_state_filename"] = "settled_terrain_data.csv"
        else:
            case["terrain"]["initial_state_case_id"] = previous_case_id
            case["terrain"]["initial_state_relative_path"] = final_state_relative_path(
                float(previous_slip)
            )
        case["test"] = copy.deepcopy(profile["test"])
        case["test"].update(
            {
                "normal_load_n": load_kg * 9.80665,
                "linear_speed_m_s": speed,
                "slip_ratios": [slip],
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
        case["sequence_condition"] = {
            "sequence": "UCF Alabama RIDER 2026-08-04",
            "lap": index,
            "split": split,
            "source_reference": str(reference_path.relative_to(project_root)),
            "source_reference_sha256": reference_sha256,
            "measured_median_active_load_kg_reported": load_kg,
            "measured_median_carriage_speed_m_s": speed,
            "measured_median_slip": slip,
            "measured_raw_median_abs_torque_nm": float(
                lap["active_abs_torque_nm"]["median"]
            ),
            "measured_tare_corrected_median_abs_torque_nm": float(
                lap["active_tare_corrected_abs_torque_nm"]["median"]
            ),
            "measured_steady_tare_corrected_median_abs_torque_nm": float(
                lap["steady_tare_corrected_abs_torque_nm"]["median"]
            ),
            "torque_qualification": (
                "Direction-conditioned loaded-stationary baseline correction; residual "
                "includes dynamic rig losses and is an upper bound on wheel-soil torque."
            ),
            "frozen_wheel_friction": wheel_friction,
            "frozen_soil_parameters_from": alabama.get("cpt_calibration_provenance"),
            "prior_case_id": previous_case_id,
            "shared_bed_case_id": bed_case_id,
            "shared_bed_state_sha256": bed_state_sha256,
        }
        destination = output_dir / f"{case_id}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)
        previous_case_id = case_id
        previous_slip = slip

    queue_path = output_dir / "alabama_rider_sequence_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "calibration_split": "laps 1-5",
                "held_out_validation_split": "laps 6-10",
                "frozen_wheel_friction": wheel_friction,
                "state_transfer": "each lap imports the preceding lap final soil state",
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
        "--output-dir", type=Path, default=Path("cases/alabama_rider_sequence_r8mm")
    )
    parser.add_argument("--wheel-friction", type=float, required=True)
    parser.add_argument("--bed-case-id", default=DEFAULT_BED_CASE_ID)
    parser.add_argument("--bed-state-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = generate(
        args.alabama.resolve(),
        args.process_profile.resolve(),
        args.reference.resolve(),
        args.output_dir.resolve(),
        args.wheel_friction,
        args.bed_case_id,
        args.bed_state_sha256,
    )
    print(f"Alabama RIDER sequence: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
