#!/usr/bin/env python3
"""Turn Alabama sensitivity outputs into an auditable parameter decision."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def scenario_metadata(master_path: Path) -> dict[str, dict[str, Any]]:
    project_root = master_path.parents[2]
    master = json.loads(master_path.read_text())
    metadata = {}
    for value in master["scenario_queues"]:
        queue_path = project_path(project_root, value)
        queue = json.loads(queue_path.read_text())
        manifest_path = project_path(project_root, queue["manifests"][0])
        manifest = json.loads(manifest_path.read_text())
        overrides = queue.get("sensitivity_overrides", {})
        metadata[queue["campaign_scenario"]] = {
            "overrides": overrides,
            "wheel_friction": float(manifest["terrain"]["wheel_friction"]),
            "time_step_s": float(manifest["terrain"]["time_step_s"]),
            "changed_parameter": next(iter(overrides), None),
            "changed_value": next(iter(overrides.values()), None),
        }
    return metadata


def complete(result: dict) -> bool:
    return result.get("completed_laps") == list(range(1, 11))


def relative_change(value: float, baseline: float) -> float | None:
    return (value - baseline) / abs(baseline) if abs(baseline) > 1e-12 else None


def load_rows(results_dir: Path, metadata: dict[str, dict[str, Any]]) -> list[dict]:
    rows = []
    for path in sorted(results_dir.glob("sensitivity-*.json")):
        if path.name == "sensitivity-summary.json":
            continue
        result = json.loads(path.read_text())
        scenario = path.stem.removeprefix("sensitivity-")
        if scenario not in metadata:
            continue
        calibration = result.get("summaries", {}).get("calibration", {})
        held_out = result.get("summaries", {}).get("held_out_validation", {})
        meta = metadata[scenario]
        rows.append(
            {
                "scenario": scenario,
                **meta,
                "status": result.get("status"),
                "completed_laps": result.get("completed_laps", []),
                "complete": complete(result),
                "calibration_completed_laps": calibration.get("completed_laps", 0),
                "calibration_relative_error": calibration.get("relative_error"),
                "calibration_median_predicted_torque_nm": calibration.get(
                    "median_predicted_contact_torque_nm"
                ),
                "held_out_completed_laps": held_out.get("completed_laps", 0),
                "held_out_relative_error": held_out.get("relative_error"),
                "held_out_median_lap_relative_error": held_out.get(
                    "median_lap_relative_error"
                ),
                "held_out_laps_within_20_percent_fraction": held_out.get(
                    "laps_within_20_percent_fraction"
                ),
                "held_out_median_predicted_torque_nm": held_out.get(
                    "median_predicted_contact_torque_nm"
                ),
                "cumulative_density_ratio_proxy": result.get("compaction", {}).get(
                    "simulated_cumulative_column_density_ratio_proxy"
                ),
                "result_json": str(path),
            }
        )
    return rows


def held_out_assessment(row: dict) -> dict:
    aggregate_error = row["held_out_relative_error"]
    fraction = row["held_out_laps_within_20_percent_fraction"]
    passes = (
        aggregate_error is not None
        and fraction is not None
        and aggregate_error <= 0.10
        and fraction >= 0.80
    )
    return {
        "status": "PASS" if passes else "FAIL",
        "aggregate_relative_error": aggregate_error,
        "median_lap_relative_error": row["held_out_median_lap_relative_error"],
        "laps_within_20_percent_fraction": fraction,
        "acceptance_limits": {
            "maximum_aggregate_relative_error": 0.10,
            "minimum_laps_within_20_percent_fraction": 0.80,
        },
    }


def evaluate(results_dir: Path, master_path: Path) -> dict:
    metadata = scenario_metadata(master_path)
    rows = load_rows(results_dir, metadata)
    friction_rows = [
        row
        for row in rows
        if row["scenario"] == "baseline"
        or row["changed_parameter"] == "wheel_friction"
    ]
    eligible = [
        row
        for row in friction_rows
        if row["complete"]
        and row["calibration_completed_laps"] == 5
        and row["held_out_completed_laps"] == 5
        and row["calibration_relative_error"] is not None
    ]
    eligible.sort(key=lambda row: (row["calibration_relative_error"], row["scenario"]))
    excluded = [
        {
            "scenario": row["scenario"],
            "wheel_friction": row["wheel_friction"],
            "completed_laps": row["completed_laps"],
            "reason": "INCOMPLETE_TEN_LAP_SEQUENCE",
        }
        for row in friction_rows
        if row not in eligible
    ]
    selected = eligible[0] if eligible else None
    selection = {
        "rule": (
            "Choose wheel friction by minimum laps 1-5 calibration aggregate error. "
            "Use laps 6-10 only as a held-out generalization test."
        ),
        "eligible_scenarios": [
            {
                "scenario": row["scenario"],
                "wheel_friction": row["wheel_friction"],
                "calibration_relative_error": row["calibration_relative_error"],
                "held_out_relative_error": row["held_out_relative_error"],
            }
            for row in eligible
        ],
        "excluded_scenarios": excluded,
        "selected_scenario": selected["scenario"] if selected else None,
        "selected_wheel_friction": selected["wheel_friction"] if selected else None,
        "calibration_relative_error": (
            selected["calibration_relative_error"] if selected else None
        ),
        "held_out_assessment": held_out_assessment(selected) if selected else None,
    }

    baseline = next((row for row in rows if row["scenario"] == "baseline"), None)
    local_sensitivity = []
    if baseline and baseline["complete"]:
        for row in rows:
            if row["scenario"] == "baseline" or not row["complete"]:
                continue
            local_sensitivity.append(
                {
                    "scenario": row["scenario"],
                    "changed_parameter": row["changed_parameter"],
                    "changed_value": row["changed_value"],
                    "calibration_predicted_torque_relative_change": relative_change(
                        row["calibration_median_predicted_torque_nm"],
                        baseline["calibration_median_predicted_torque_nm"],
                    ),
                    "held_out_predicted_torque_relative_change": relative_change(
                        row["held_out_median_predicted_torque_nm"],
                        baseline["held_out_median_predicted_torque_nm"],
                    ),
                    "cumulative_density_proxy_relative_change": relative_change(
                        row["cumulative_density_ratio_proxy"] - 1.0,
                        baseline["cumulative_density_ratio_proxy"] - 1.0,
                    ),
                }
            )
    sensitivity_status = (
        "AVAILABLE"
        if baseline and baseline["complete"]
        else "WITHHELD_BASELINE_INCOMPLETE"
    )

    timestep_rows = {
        row["scenario"]: row
        for row in rows
        if row["scenario"] in {"baseline", "timestep2p5us", "timestep7p5us"}
    }
    timestep_complete = all(
        name in timestep_rows and timestep_rows[name]["complete"]
        for name in ("baseline", "timestep2p5us", "timestep7p5us")
    )
    timestep_check = {
        "status": "AVAILABLE" if timestep_complete else "WITHHELD_INCOMPLETE",
        "qualification": (
            "The 2.5 us case is the refinement check against the 5 us baseline; the "
            "7.5 us case is a coarsening sensitivity. No absolute compaction claim follows."
        ),
        "scenarios": [
            {
                "scenario": name,
                "time_step_s": timestep_rows[name]["time_step_s"],
                "complete": timestep_rows[name]["complete"],
                "calibration_median_predicted_torque_nm": timestep_rows[name][
                    "calibration_median_predicted_torque_nm"
                ],
                "cumulative_density_ratio_proxy": timestep_rows[name][
                    "cumulative_density_ratio_proxy"
                ],
            }
            for name in ("baseline", "timestep2p5us", "timestep7p5us")
            if name in timestep_rows
        ],
    }
    if timestep_complete:
        fine = timestep_rows["timestep2p5us"]
        base = timestep_rows["baseline"]
        timestep_check["refinement_relative_changes"] = {
            "calibration_predicted_torque": relative_change(
                fine["calibration_median_predicted_torque_nm"],
                base["calibration_median_predicted_torque_nm"],
            ),
            "cumulative_density_gain_proxy": relative_change(
                fine["cumulative_density_ratio_proxy"] - 1.0,
                base["cumulative_density_ratio_proxy"] - 1.0,
            ),
        }

    status = "WITHHELD_NO_COMPLETE_WHEEL_FRICTION_CASE"
    if selected:
        status = (
            "PARAMETER_SELECTED_HELD_OUT_PASS"
            if selection["held_out_assessment"]["status"] == "PASS"
            else "PARAMETER_SELECTED_HELD_OUT_FAIL"
        )
    return {
        "schema_version": 1,
        "status": status,
        "evidence_role": "calibration_selection_and_held_out_assessment",
        "wheel_friction_selection": selection,
        "local_sensitivity": {
            "status": sensitivity_status,
            "comparisons_to_baseline": local_sensitivity,
        },
        "time_step_sensitivity": timestep_check,
        "qualification": (
            "This decision applies to RIDER torque reproduction on the fixed coarse 8 mm "
            "bed. Absolute compaction remains withheld until density/resolution convergence "
            "and matched physical validation are complete."
        ),
        "scenarios": rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["scenarios"]
    if rows:
        fields = [
            "scenario",
            "changed_parameter",
            "changed_value",
            "wheel_friction",
            "time_step_s",
            "status",
            "complete",
            "calibration_relative_error",
            "held_out_relative_error",
            "held_out_median_lap_relative_error",
            "held_out_laps_within_20_percent_fraction",
            "cumulative_density_ratio_proxy",
        ]
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.results_dir.resolve(), args.master.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    selection = result["wheel_friction_selection"]
    print(
        f"wheel friction={selection['selected_wheel_friction']}, "
        f"held out={selection['held_out_assessment']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
