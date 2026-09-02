#!/usr/bin/env python3
"""Create the smallest gated RIDER/CRATR retest matrix from DEM outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def dominates(left: dict, right: dict) -> bool:
    no_worse = (
        left["density_ratio_gain_vs_smooth"]
        >= right["density_ratio_gain_vs_smooth"]
        and left["drawbar_vs_smooth"] >= right["drawbar_vs_smooth"]
        and left["torque_vs_smooth"] <= right["torque_vs_smooth"]
    )
    strictly_better = (
        left["density_ratio_gain_vs_smooth"]
        > right["density_ratio_gain_vs_smooth"]
        or left["drawbar_vs_smooth"] > right["drawbar_vs_smooth"]
        or left["torque_vs_smooth"] < right["torque_vs_smooth"]
    )
    return no_worse and strictly_better


def pareto_frontier(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if not any(dominates(other, row) for other in rows if other is not row)
    ]


def test_rows(wheels: list[dict], phase: str) -> list[dict]:
    rows = []
    for wheel in wheels:
        for reset in range(1, 4):
            rows.append(
                {
                    "phase": phase,
                    "wheel": wheel["wheel"],
                    "role": wheel["role"],
                    "bed_reset": reset,
                    "traffic_laps": 10,
                    "cpt_checkpoints_after_lap": "0;1;5;10",
                    "cpt_spatial_readings_per_checkpoint": 3,
                    "normal_load_control": "target within +/-5%",
                    "speed_control": "target within +/-10%",
                    "slip_control": "record carriage and wheel encoders; mean <=20%",
                }
            )
    return rows


def build(candidate_summary: Path, repeatability_summary: Path) -> dict:
    candidates = json.loads(candidate_summary.read_text())
    repeatability = json.loads(repeatability_summary.read_text())
    repeatability_pass = repeatability.get("status") == "PASS_PROVISIONAL"
    comparable = [
        row
        for row in candidates.get("candidates", [])
        if row.get("candidate") != "smooth_control"
        and row.get("completed_laps") == 10
        and row.get("density_ratio_gain_vs_smooth") is not None
        and row.get("drawbar_vs_smooth") is not None
        and row.get("torque_vs_smooth") is not None
    ]
    mobility_gated = [
        row
        for row in comparable
        if row["torque_vs_smooth"] <= 1.25
        and row["drawbar_vs_smooth"] >= 0.80
        and row["density_ratio_gain_vs_smooth"] >= 1.0
    ]
    frontier = pareto_frontier(mobility_gated)
    frontier.sort(
        key=lambda row: (
            -row["density_ratio_gain_vs_smooth"],
            -row["drawbar_vs_smooth"],
            row["torque_vs_smooth"],
            row["candidate"],
        )
    )
    selected = frontier[:2]
    mvp_wheels = [
        {"wheel": "alabama_reference", "role": "calibration anchor"},
        {"wheel": "smooth_control", "role": "bed and rig control"},
    ]
    if selected:
        mvp_wheels.append(
            {"wheel": selected[0]["candidate"], "role": "DEM-selected candidate"}
        )
    expansion_wheels = (
        [
            {
                "wheel": selected[1]["candidate"],
                "role": "second Pareto candidate",
            }
        ]
        if len(selected) > 1
        else []
    )
    status = (
        "READY_MVP_RETEST"
        if repeatability_pass and selected
        else "HOLD_NO_ELIGIBLE_CANDIDATE"
        if repeatability_pass
        else "HOLD_NUMERICAL_REPEATABILITY_GATE"
    )
    matrix = test_rows(mvp_wheels, "MVP")
    matrix.extend(test_rows(expansion_wheels, "CONDITIONAL_EXPANSION"))
    return {
        "schema_version": 1,
        "status": status,
        "decision_gate": {
            "numerical_repeatability_status": repeatability.get("status"),
            "candidate_screen_status": candidates.get("status"),
            "provisional_candidate_limits": {
                "maximum_torque_vs_smooth": 1.25,
                "minimum_drawbar_vs_smooth": 0.80,
                "minimum_density_gain_vs_smooth": 1.0,
            },
            "qualification": (
                "These are proposed down-selection limits for an efficient physical test, "
                "not contract acceptance thresholds."
            ),
        },
        "pareto_candidates": [
            {
                "candidate": row["candidate"],
                "density_ratio_gain_vs_smooth": row[
                    "density_ratio_gain_vs_smooth"
                ],
                "drawbar_vs_smooth": row["drawbar_vs_smooth"],
                "torque_vs_smooth": row["torque_vs_smooth"],
            }
            for row in frontier
        ],
        "mvp_wheels": mvp_wheels,
        "conditional_expansion_wheels": expansion_wheels,
        "test_matrix": matrix,
        "required_record": {
            "bed": [
                "simulant name, lot, dry mass, moisture, bin geometry",
                "repeatable preparation procedure and achieved bulk density",
                "surface profile and CPT before traffic and after laps 1, 5, and 10",
                "three in-lane spatial CPT readings at every checkpoint",
            ],
            "rig": [
                "wheel CAD/OBJ/print revision and mounted dimensions",
                "normal load, carriage speed, wheel angular speed, calculated slip",
                "tare-corrected torque with calibration and sample rate",
                "carriage and wheel encoder time series with synchronized timestamps",
            ],
            "execution": [
                "three independent bed resets per wheel",
                "randomized or blocked wheel order",
                "same stop/reject rules for every wheel",
            ],
        },
        "expansion_rule": (
            "Run the second Pareto candidate only after the Alabama and smooth controls "
            "meet the test card repeatability and data-completeness gates."
        ),
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["test_matrix"]
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-summary", type=Path, required=True)
    parser.add_argument("--repeatability-summary", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = build(
        args.candidate_summary.resolve(), args.repeatability_summary.resolve()
    )
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
