#!/usr/bin/env python3
"""Compare repeated-traffic DEM trends with held-out RTGS CPT campaigns."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def mean_reading(point: dict) -> float:
    return statistics.mean(float(reading["value"]) for reading in point["readings"])


def monotonic_fraction(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return sum(right >= left for left, right in zip(values, values[1:])) / (
        len(values) - 1
    )


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right)
    )
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def normalized(values: list[float]) -> list[float] | None:
    maximum = max(values, default=0.0)
    if maximum <= 0:
        return None
    return [value / maximum for value in values]


def evaluate_campaign(campaign: dict, simulated_by_lap: dict[int, float]) -> dict:
    points = [
        point
        for point in campaign["points"]
        if 0 <= int(point["laps_completed"]) <= max(simulated_by_lap)
        and int(point["laps_completed"]) in simulated_by_lap
    ]
    points.sort(key=lambda point: int(point["laps_completed"]))
    if not points or int(points[0]["laps_completed"]) != 0:
        raise ValueError(f"Campaign {campaign['campaign_id']} lacks a matched lap-zero point")
    physical_values = [mean_reading(point) for point in points]
    physical_gain = [value - physical_values[0] for value in physical_values]
    simulated_gain = [simulated_by_lap[int(point["laps_completed"])] for point in points]
    physical_normalized = normalized(physical_gain)
    simulated_normalized = normalized(simulated_gain)
    comparable_physical = physical_gain[1:]
    comparable_simulated = simulated_gain[1:]
    physical_norm_nonzero = normalized(comparable_physical)
    simulated_norm_nonzero = normalized(comparable_simulated)
    shape_correlation = (
        pearson(physical_norm_nonzero, simulated_norm_nonzero)
        if physical_norm_nonzero is not None and simulated_norm_nonzero is not None
        else None
    )
    mean_absolute_shape_error = (
        statistics.mean(
            abs(observed - predicted)
            for observed, predicted in zip(
                physical_norm_nonzero, simulated_norm_nonzero
            )
        )
        if physical_norm_nonzero is not None and simulated_norm_nonzero is not None
        else None
    )
    return {
        "campaign_id": campaign["campaign_id"],
        "replicate": campaign["replicate"],
        "matched_laps": [int(point["laps_completed"]) for point in points],
        "physical_baseline_reported_value": physical_values[0],
        "physical_final_gain_reported_value": physical_gain[-1],
        "simulated_final_density_gain_proxy": simulated_gain[-1],
        "physical_monotonic_step_fraction": monotonic_fraction(physical_values),
        "simulated_monotonic_step_fraction": monotonic_fraction(simulated_gain),
        "normalized_shape_pearson": shape_correlation,
        "normalized_shape_mean_absolute_error": mean_absolute_shape_error,
        "curve": [
            {
                "lap": int(point["laps_completed"]),
                "physical_mean_reported_value": physical,
                "physical_gain_from_lap_zero": physical_delta,
                "physical_normalized_gain": (
                    physical_normalized[index]
                    if physical_normalized is not None
                    else None
                ),
                "simulated_density_gain_proxy": simulated,
                "simulated_normalized_gain": (
                    simulated_normalized[index]
                    if simulated_normalized is not None
                    else None
                ),
            }
            for index, (point, physical, physical_delta, simulated) in enumerate(
                zip(points, physical_values, physical_gain, simulated_gain)
            )
        ],
    }


def evaluate(output_root: Path, penetrometer_reference: Path) -> dict:
    reference = json.loads(penetrometer_reference.read_text())
    grouped: dict[str, list[dict]] = {}
    for result_path in sorted(
        output_root.glob("rtgs-cpt-sequence-*-lap*/wheel_performance.json")
    ):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        target = manifest.get("rtgs_penetrometer_target")
        if not target:
            continue
        strain = float(result["lane"]["column_strain_proxy"])
        grouped.setdefault(target["design"], []).append(
            {
                "lap": int(target["lap"]),
                "density_ratio_increment": 1.0 / (1.0 - strain),
                "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
                "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
                "drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "density_gate_status": result["density_gate"]["status"],
                "result_json": str(result_path),
            }
        )

    if not grouped:
        raise ValueError(f"No completed RTGS CPT sequence cases found in {output_root}")

    design_results = []
    for design, laps in sorted(grouped.items()):
        laps.sort(key=lambda row: row["lap"])
        cumulative_density_ratio = 1.0
        simulated_by_lap = {0: 0.0}
        for row in laps:
            cumulative_density_ratio *= row["density_ratio_increment"]
            simulated_by_lap[row["lap"]] = cumulative_density_ratio - 1.0
        campaigns = [
            campaign
            for campaign in reference["campaigns"]
            if campaign["wheel_design"] == design
        ]
        campaign_results = [
            evaluate_campaign(campaign, simulated_by_lap) for campaign in campaigns
        ]
        correlations = [
            campaign["normalized_shape_pearson"]
            for campaign in campaign_results
            if campaign["normalized_shape_pearson"] is not None
        ]
        design_results.append(
            {
                "design": design,
                "completed_laps": len(laps),
                "completed_lap_numbers": [row["lap"] for row in laps],
                "simulated_cumulative_density_ratio_proxy": cumulative_density_ratio,
                "simulated_cumulative_settlement_m": sum(
                    row["settlement_m"] for row in laps
                ),
                "simulated_median_contact_torque_nm": statistics.median(
                    row["torque_nm"] for row in laps
                ),
                "simulated_median_drawbar_to_normal": statistics.median(
                    row["drawbar_to_normal"] for row in laps
                ),
                "all_density_gates_pass": all(
                    row["density_gate_status"] == "PASS_DENSITY" for row in laps
                ),
                "median_normalized_shape_pearson": (
                    statistics.median(correlations) if correlations else None
                ),
                "physical_campaigns": campaign_results,
            }
        )

    complete = {row["design"] for row in design_results} == {
        "Closed_SIU",
        "Closed_Scalloped",
    } and all(row["completed_laps"] == 50 for row in design_results)
    return {
        "schema_version": 1,
        "status": "COMPLETE_TREND_VALIDATION_ONLY" if complete else "PARTIAL",
        "evidence_role": "held_out_validation",
        "penetrometer_reference": str(penetrometer_reference),
        "qualification": (
            "Physical values retain the workbook's reported kg/cm^2 unit. DEM is compared "
            "only through normalized trend shape, monotonicity, and relative densification. "
            "The 8 mm bed density mismatch and particle-to-cone scale preclude absolute "
            "virtual-CPT claims. RTGS data are not used to refit parameters."
        ),
        "designs": design_results,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = []
    for design in result["designs"]:
        for campaign in design["physical_campaigns"]:
            rows.append(
                {
                    "design": design["design"],
                    "completed_laps": design["completed_laps"],
                    "campaign_id": campaign["campaign_id"],
                    "replicate": campaign["replicate"],
                    "physical_final_gain_reported_value": campaign[
                        "physical_final_gain_reported_value"
                    ],
                    "simulated_final_density_gain_proxy": campaign[
                        "simulated_final_density_gain_proxy"
                    ],
                    "physical_monotonic_step_fraction": campaign[
                        "physical_monotonic_step_fraction"
                    ],
                    "simulated_monotonic_step_fraction": campaign[
                        "simulated_monotonic_step_fraction"
                    ],
                    "normalized_shape_pearson": campaign[
                        "normalized_shape_pearson"
                    ],
                    "normalized_shape_mean_absolute_error": campaign[
                        "normalized_shape_mean_absolute_error"
                    ],
                }
            )
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("physical_references/rtgs_cone_penetrometer_2024.json"),
    )
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve(), args.reference.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    for row in result["designs"]:
        print(
            f"{row['design']}: laps={row['completed_laps']}, "
            f"median shape r={row['median_normalized_shape_pearson']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
