#!/usr/bin/env python3
"""Generate held-out repeated-traffic cases for RTGS CPT validation."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file
from generate_alabama_friction_sweep import (
    DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
    DEFAULT_BED_CASE_ID,
    DEFAULT_BED_PREPARATION_SHA256,
    DEFAULT_BED_TARGET_DENSITY_KG_M3,
)
from generate_alabama_lap_sequence import final_state_relative_path


DESIGNS = {
    "Closed_Scalloped": "screen-cratr_w002_closed_scalloped-coarse-cpt-informed.json",
    "Closed_SIU": "screen-cratr_w003_closed_siu-coarse-cpt-informed.json",
}


def slug(value: str) -> str:
    return value.lower().replace("_", "-")


def generate(
    telemetry_path: Path,
    penetrometer_path: Path,
    case_dir: Path,
    process_profile_path: Path,
    output_dir: Path,
    wheel_friction: float,
    bed_case_id: str = DEFAULT_BED_CASE_ID,
    bed_state_sha256: str | None = None,
) -> Path:
    if wheel_friction <= 0:
        raise ValueError("Wheel friction must be positive")
    telemetry = json.loads(telemetry_path.read_text())
    penetrometer = json.loads(penetrometer_path.read_text())
    profile = json.loads(process_profile_path.read_text())
    try:
        cases_root = next(parent for parent in case_dir.parents if parent.name == "cases")
    except StopIteration as exc:
        raise ValueError("Case directory must be stored below a cases directory") from exc
    project_root = cases_root.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    design_queues = []

    for design, filename in DESIGNS.items():
        base = json.loads((case_dir / filename).read_text())
        laps = telemetry["designs"][design]["laps"]
        if len(laps) != 50:
            raise ValueError(f"Expected 50 telemetry laps for {design}, found {len(laps)}")
        physical_campaigns = [
            campaign["campaign_id"]
            for campaign in penetrometer["campaigns"]
            if campaign["wheel_design"] == design
        ]
        if len(physical_campaigns) < 2:
            raise ValueError(f"Expected at least two CPT campaigns for {design}")

        destination_dir = output_dir / slug(design)
        destination_dir.mkdir(parents=True, exist_ok=True)
        manifests = []
        previous_case_id = None
        previous_slip = None
        for lap_number, measured in enumerate(laps, 1):
            load_kg = float(measured["active_load_kg_reported"]["median"])
            speed = float(measured["derived_carriage_speed_m_s"]["median"])
            slip = float(measured["derived_slip"]["median"])
            case = copy.deepcopy(base)
            case_id = f"rtgs-cpt-sequence-{slug(design)}-lap{lap_number:02d}"
            case["case_id"] = case_id
            case["model_status"] = "alabama_calibrated_rtgs_held_out_trend_validation"
            case["purpose"] = (
                "Test whether the frozen Alabama/CPT-informed DEM reproduces the held-out "
                f"RTGS {design} repeated-traffic compaction trend."
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
                "source_preparation_path": f"case:{bed_case_id}/terrain/terrain_preparation.json",
                "source_preparation_sha256": DEFAULT_BED_PREPARATION_SHA256,
                "target_bulk_density_kg_m3": DEFAULT_BED_TARGET_DENSITY_KG_M3,
                "post_release_bulk_density_kg_m3": DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
                "achieved_to_target_ratio": (
                    DEFAULT_BED_ACHIEVED_DENSITY_KG_M3
                    / DEFAULT_BED_TARGET_DENSITY_KG_M3
                ),
                "random_seed": 77,
            }
            case["rtgs_penetrometer_target"] = {
                "design": design,
                "lap": lap_number,
                "split": "held_out_validation",
                "telemetry_reference": str(telemetry_path.relative_to(project_root)),
                "telemetry_reference_sha256": sha256_file(telemetry_path),
                "penetrometer_reference": str(penetrometer_path.relative_to(project_root)),
                "penetrometer_reference_sha256": sha256_file(penetrometer_path),
                "physical_campaign_ids": physical_campaigns,
                "measured_median_active_load_kg_reported": load_kg,
                "measured_median_carriage_speed_m_s": speed,
                "measured_median_slip": slip,
                "frozen_wheel_friction": wheel_friction,
                "prior_case_id": previous_case_id,
                "shared_bed_case_id": bed_case_id,
                "shared_bed_state_sha256": bed_state_sha256,
                "qualification": (
                    "Compare normalized compaction trend and monotonicity only. Current DEM "
                    "particle scale does not support absolute virtual-CPT prediction."
                ),
            }
            destination = destination_dir / f"{case_id}.json"
            destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
            manifests.append(destination)
            previous_case_id = case_id
            previous_slip = slip

        queue_path = destination_dir / "sequence_queue.json"
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "design": design,
                    "manifests": [
                        str(path.relative_to(project_root)) for path in manifests
                    ],
                    "validation_split": "all physical CPT campaigns are held out",
                    "state_transfer": "each lap imports the preceding lap final soil state",
                    "physical_campaign_ids": physical_campaigns,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        design_queues.append(queue_path)

    master_path = output_dir / "rtgs_penetrometer_campaign.json"
    master_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign": "RTGS repeated-traffic held-out CPT trend validation",
                "design_queues": [
                    str(path.relative_to(project_root)) for path in design_queues
                ],
                "interpretation": (
                    "Use physical CPT campaign replicates as trend envelopes. Do not refit "
                    "soil or contact parameters on RTGS results."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return master_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=Path("physical_references/rtgs_rider_historical.json"),
    )
    parser.add_argument(
        "--penetrometer",
        type=Path,
        default=Path("physical_references/rtgs_cone_penetrometer_2024.json"),
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
        "--output-dir", type=Path, default=Path("cases/rtgs_penetrometer_sequences_r8mm")
    )
    parser.add_argument("--wheel-friction", type=float, default=0.9)
    parser.add_argument("--bed-case-id", default=DEFAULT_BED_CASE_ID)
    parser.add_argument("--bed-state-sha256")
    args = parser.parse_args()
    master = generate(
        args.telemetry.resolve(),
        args.penetrometer.resolve(),
        args.case_dir.resolve(),
        args.process_profile.resolve(),
        args.output_dir.resolve(),
        args.wheel_friction,
        args.bed_case_id,
        args.bed_state_sha256,
    )
    print(f"RTGS CPT campaign: {master}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
