#!/usr/bin/env python3
"""Generate chained Alabama sequences for a bounded one-factor sensitivity study."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from generate_alabama_lap_sequence import final_state_relative_path


DEFAULT_SCENARIOS = {
    "baseline": {},
    "wheel_mu0p75": {"wheel_friction": 0.75},
    "wheel_mu0p825": {"wheel_friction": 0.825},
    "wheel_mu0p975": {"wheel_friction": 0.975},
    "wheel_mu1p05": {"wheel_friction": 1.05},
    "particle_mu0p4": {"particle_friction": 0.4},
    "particle_mu0p6": {"particle_friction": 0.6},
    "rolling0p05": {"rolling_resistance": 0.05},
    "rolling0p15": {"rolling_resistance": 0.15},
    "youngs150mpa": {"youngs_modulus_pa": 150_000_000.0},
    "youngs600mpa": {"youngs_modulus_pa": 600_000_000.0},
    "restitution0p1": {"coefficient_of_restitution": 0.1},
    "restitution0p5": {"coefficient_of_restitution": 0.5},
    "timestep2p5us": {"time_step_s": 2.5e-6},
    "timestep7p5us": {"time_step_s": 7.5e-6},
}


def generate(
    base_queue_path: Path,
    output_dir: Path,
    scenarios: dict[str, dict[str, float]] = DEFAULT_SCENARIOS,
) -> Path:
    base_queue = json.loads(base_queue_path.read_text())
    project_root = base_queue_path.parents[2]
    base_manifests = []
    for value in base_queue["manifests"]:
        path = Path(value)
        if not path.is_absolute():
            path = project_root / path
        base_manifests.append(path)
    if len(base_manifests) != 10:
        raise ValueError(f"Expected 10 Alabama sequence manifests, found {len(base_manifests)}")
    if "baseline" not in scenarios:
        raise ValueError("Sensitivity campaign must include a baseline scenario")

    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_queues = []
    for scenario, overrides in scenarios.items():
        if not scenario or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in scenario):
            raise ValueError(f"Invalid scenario identifier: {scenario!r}")
        scenario_dir = output_dir / scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)
        manifests = []
        previous_case_id = None
        previous_slip = None
        for lap, base_path in enumerate(base_manifests, 1):
            case = copy.deepcopy(json.loads(base_path.read_text()))
            case_id = f"alabama-sensitivity-{scenario}-lap{lap:02d}"
            case["case_id"] = case_id
            case["model_status"] = "cpt_informed_alabama_one_factor_sensitivity"
            case["purpose"] = (
                "Measure local DEM sensitivity around the frozen CPT and Alabama calibration. "
                "Only the declared terrain field changes from the baseline, and laps 6-10 "
                "remain held out from calibration."
            )
            case["terrain"].update(overrides)
            if previous_case_id is not None:
                case["terrain"]["initial_state_case_id"] = previous_case_id
                case["terrain"].pop("initial_state_filename", None)
                case["terrain"]["initial_state_relative_path"] = final_state_relative_path(
                    float(previous_slip)
                )
            condition = case["sequence_condition"]
            condition["campaign_scenario"] = scenario
            condition["sensitivity_overrides"] = overrides
            condition["one_factor_at_a_time"] = len(overrides) <= 1
            condition["qualification"] = (
                "Local sensitivity on one frozen 8 mm bed geometry. Soil-property variants "
                "are not independent CPT recalibrations and must not replace the CPT-selected baseline."
            )
            condition["frozen_wheel_friction"] = float(case["terrain"]["wheel_friction"])
            destination = scenario_dir / f"{case_id}.json"
            destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
            manifests.append(destination)
            previous_case_id = case_id
            previous_slip = float(case["test"]["slip_ratios"][0])

        queue_path = scenario_dir / "sequence_queue.json"
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "campaign_scenario": scenario,
                    "sensitivity_overrides": overrides,
                    "manifests": [
                        str(path.relative_to(project_root)) for path in manifests
                    ],
                    "calibration_split": "laps 1-5",
                    "held_out_validation_split": "laps 6-10",
                    "state_transfer": "each lap imports the preceding lap final soil state",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        scenario_queues.append(queue_path)

    master_path = output_dir / "sensitivity_campaign.json"
    master_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign": "Alabama RIDER one-factor sensitivity",
                "baseline_queue": str(base_queue_path.relative_to(project_root)),
                "scenario_queues": [
                    str(path.relative_to(project_root)) for path in scenario_queues
                ],
                "interpretation": (
                    "Select wheel friction using laps 1-5 only. Use laps 6-10 to assess "
                    "generalization. Treat soil-property and timestep cases as sensitivity, "
                    "not additional fitted parameter sets."
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
        "--base-queue",
        type=Path,
        default=Path(
            "cases/alabama_rider_sequence_mu0p9_r8mm/alabama_rider_sequence_queue.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/refinement_sensitivity_r8mm")
    )
    args = parser.parse_args()
    master = generate(args.base_queue.resolve(), args.output_dir.resolve())
    print(f"Sensitivity campaign: {master}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
