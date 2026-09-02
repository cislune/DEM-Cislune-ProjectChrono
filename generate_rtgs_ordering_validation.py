#!/usr/bin/env python3
"""Generate bounded RTGS RIDER wheel-ordering validation cases."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import statistics

from dem_case_runner import sha256_file
from generate_alabama_friction_sweep import (
    DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
    DEFAULT_BED_CASE_ID,
    DEFAULT_BED_PREPARATION_SHA256,
    DEFAULT_BED_TARGET_DENSITY_KG_M3,
)


DESIGNS = {
    "Closed_Sharp": "screen-cratr_w001_closed_sharp_smooth-coarse-cpt-informed.json",
    "Closed_Scalloped": "screen-cratr_w002_closed_scalloped-coarse-cpt-informed.json",
    "Closed_SIU": "screen-cratr_w003_closed_siu-coarse-cpt-informed.json",
}


def generate(
    reference_path: Path,
    case_dir: Path,
    process_profile_path: Path,
    output_dir: Path,
    wheel_friction: float,
    bed_case_id: str = DEFAULT_BED_CASE_ID,
    bed_state_sha256: str | None = None,
) -> Path:
    reference = json.loads(reference_path.read_text())
    profile = json.loads(process_profile_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        cases_root = next(parent for parent in case_dir.parents if parent.name == "cases")
    except StopIteration:
        cases_root = case_dir.parent
    project_root = cases_root.parent
    manifests = []
    for design, filename in DESIGNS.items():
        campaign = reference["designs"][design]
        base = json.loads((case_dir / filename).read_text())
        loads = [
            float(lap["active_load_kg_reported"]["median"])
            for lap in campaign["laps"]
            if lap["active_load_kg_reported"]["median"] is not None
        ]
        speeds = [
            float(lap["derived_carriage_speed_m_s"]["median"])
            for lap in campaign["laps"]
            if lap["derived_carriage_speed_m_s"]["median"] is not None
        ]
        load_kg = statistics.median(loads)
        speed = statistics.median(speeds)
        slip = float(campaign["median_of_lap_median_slip"])
        case = copy.deepcopy(base)
        case["case_id"] = f"validate-rtgs-{design.lower()}-r8mm-frozen"
        case["model_status"] = "cpt_and_alabama_informed_rtgs_ordinal_pilot"
        case["purpose"] = (
            "With CPT-selected soil and Alabama-selected wheel friction frozen, test whether "
            "DEM reproduces the historical RIDER motor-demand ordering across three wheel geometries."
        )
        case["terrain"] = copy.deepcopy(profile["terrain"])
        case["terrain"].update(
            {
                "initial_state_case_id": bed_case_id,
                "initial_state_filename": "settled_terrain_data.csv",
                "wheel_friction": wheel_friction,
            }
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
            "source_preparation_sha256": DEFAULT_BED_PREPARATION_SHA256,
            "target_bulk_density_kg_m3": DEFAULT_BED_TARGET_DENSITY_KG_M3,
            "post_release_bulk_density_kg_m3": DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
            "achieved_to_target_ratio": (
                DEFAULT_BED_ACHIEVED_DENSITY_KG_M3
                / DEFAULT_BED_TARGET_DENSITY_KG_M3
            ),
            "random_seed": 77,
        }
        case["ordinal_validation_target"] = {
            "design": design,
            "source_reference": str(reference_path.relative_to(project_root)),
            "source_reference_sha256": sha256_file(reference_path),
            "lap_files": int(campaign["lap_files"]),
            "median_of_lap_median_abs_current_reading": float(
                campaign["median_of_lap_median_abs_current_reading"]
            ),
            "measured_median_load_kg_reported": load_kg,
            "measured_median_carriage_speed_m_s": speed,
            "measured_median_slip": slip,
            "frozen_wheel_friction": wheel_friction,
            "shared_bed_case_id": bed_case_id,
            "shared_bed_state_sha256": bed_state_sha256,
            "qualification": (
                "The historical currentReading units are unknown. Validate rank ordering only; "
                "do not compare current magnitude with DEM torque."
            ),
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    queue = output_dir / "rtgs_ordering_validation_queue.json"
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "comparison": (
                    "Rank DEM median wheel-contact torque against historical median motor-current ordering."
                ),
                "frozen_wheel_friction": wheel_friction,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("physical_references/rtgs_rider_historical.json"),
    )
    parser.add_argument("--case-dir", type=Path, default=Path("cases/wheel_screen_cpt"))
    parser.add_argument(
        "--process-profile",
        type=Path,
        default=Path(
            "cases/wheel_phase_screen_r8mm_dt5us_1p2s/"
            "process-smooth_control-r8mm-dt5us-phase1p2s.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/rtgs_ordering_validation_r8mm")
    )
    parser.add_argument("--wheel-friction", type=float, required=True)
    parser.add_argument("--bed-case-id", default=DEFAULT_BED_CASE_ID)
    parser.add_argument("--bed-state-sha256")
    args = parser.parse_args()
    queue = generate(
        args.reference.resolve(),
        args.case_dir.resolve(),
        args.process_profile.resolve(),
        args.output_dir.resolve(),
        args.wheel_friction,
        args.bed_case_id,
        args.bed_state_sha256,
    )
    print(f"RTGS ordering queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
