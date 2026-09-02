#!/usr/bin/env python3
"""Evaluate the chained Alabama sequence without tuning on held-out laps."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def evaluate(output_root: Path, scenario: str | None = None) -> dict:
    rows = []
    pattern = (
        "*/wheel_performance.json"
        if scenario is not None
        else "alabama-rider-sequence-mu*-lap*/wheel_performance.json"
    )
    for result_path in sorted(output_root.glob(pattern)):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        condition = manifest.get("sequence_condition")
        if not condition:
            continue
        if scenario is not None and condition.get("campaign_scenario") != scenario:
            continue
        predicted = float(result["mobility"]["torque_y_nm"]["median_abs"])
        observed = float(
            condition["measured_tare_corrected_median_abs_torque_nm"]
        )
        strain = float(result["lane"]["column_strain_proxy"])
        rows.append(
            {
                "lap": int(condition["lap"]),
                "split": condition["split"],
                "predicted_contact_torque_nm": predicted,
                "observed_corrected_torque_upper_bound_nm": observed,
                "predicted_to_observed_ratio": predicted / observed,
                "absolute_error_nm": abs(predicted - observed),
                "relative_error": abs(predicted - observed) / observed,
                "incremental_column_strain_proxy": strain,
                "incremental_density_ratio_proxy": 1.0 / (1.0 - strain),
                "density_gate_status": result["density_gate"]["status"],
                "result_status": result["status"],
                "result_json": str(result_path),
            }
        )
    rows.sort(key=lambda row: row["lap"])
    if not rows:
        raise ValueError(f"No completed Alabama sequence cases found in {output_root}")

    summaries = {}
    for split in ("calibration", "held_out_validation"):
        selected = [row for row in rows if row["split"] == split]
        if not selected:
            continue
        predicted = statistics.median(
            row["predicted_contact_torque_nm"] for row in selected
        )
        observed = statistics.median(
            row["observed_corrected_torque_upper_bound_nm"] for row in selected
        )
        summaries[split] = {
            "completed_laps": len(selected),
            "median_predicted_contact_torque_nm": predicted,
            "median_observed_corrected_torque_upper_bound_nm": observed,
            "predicted_to_observed_ratio": predicted / observed,
            "relative_error": abs(predicted - observed) / observed,
            "median_lap_relative_error": statistics.median(
                row["relative_error"] for row in selected
            ),
            "maximum_lap_relative_error": max(
                row["relative_error"] for row in selected
            ),
            "laps_within_20_percent_fraction": sum(
                row["relative_error"] <= 0.20 for row in selected
            )
            / len(selected),
            "outlier_laps_over_50_percent": [
                row["lap"] for row in selected if row["relative_error"] > 0.50
            ],
        }

    cumulative_density_ratio = 1.0
    for row in rows:
        cumulative_density_ratio *= row["incremental_density_ratio_proxy"]
    all_complete = [row["lap"] for row in rows] == list(range(1, 11))
    density_mismatch = any(
        row["density_gate_status"] != "PASS_DENSITY" for row in rows
    )
    held_out = summaries.get("held_out_validation")
    if not all_complete or held_out is None:
        torque_validation_status = "PARTIAL"
    elif (
        held_out["relative_error"] <= 0.10
        and held_out["laps_within_20_percent_fraction"] >= 0.80
    ):
        torque_validation_status = (
            "PASS_MEDIAN_WITH_OUTLIER"
            if held_out["outlier_laps_over_50_percent"]
            else "PASS"
        )
    else:
        torque_validation_status = "FAIL"
    return {
        "schema_version": 1,
        "status": (
            f"COMPLETE_{torque_validation_status}_DENSITY_MISMATCH"
            if all_complete and density_mismatch
            else f"COMPLETE_{torque_validation_status}"
            if all_complete
            else "PARTIAL"
        ),
        "torque_validation_status": torque_validation_status,
        "completed_laps": [row["lap"] for row in rows],
        "summaries": summaries,
        "compaction": {
            "simulated_cumulative_column_density_ratio_proxy": cumulative_density_ratio,
            "observed_in_to_out_bulk_density_ratio": 1.1403051895871694,
            "observed_in_to_out_q100_ratio": 7.734322319622387,
            "qualification": (
                "The DEM value is a chained lane-height proxy, not a simulated CPT result. "
                "The 8 mm bed density gate fails, and the physical CPT samples are spatial "
                "post-traffic contrasts. Use this comparison for direction and scale only."
            ),
        },
        "interpretation": (
            "Physical torque is corrected by a same-lap, same-direction loaded-stationary "
            "baseline but still contains dynamic rig losses, so it is an upper bound on "
            "wheel-soil contact torque. Laps 6-10 are held out from friction selection."
        ),
        "laps": rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["laps"]
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    parser.add_argument("--scenario")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve(), args.scenario)
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    for split, summary in result["summaries"].items():
        print(
            f"{split}: predicted={summary['median_predicted_contact_torque_nm']:.3f} Nm, "
            f"observed_upper_bound={summary['median_observed_corrected_torque_upper_bound_nm']:.3f} Nm, "
            f"error={summary['relative_error']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
