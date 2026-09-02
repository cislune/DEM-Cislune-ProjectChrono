#!/usr/bin/env python3
"""Summarize same-bed numerical variability for wheel DEM metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def variation(values: list[float]) -> dict:
    mean = statistics.mean(values)
    standard_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "sample_standard_deviation": standard_deviation,
        "coefficient_of_variation": (
            standard_deviation / abs(mean) if abs(mean) > 1e-12 else None
        ),
    }


def evaluate(output_root: Path) -> dict:
    grouped: dict[str, list[dict]] = {}
    expected = {}
    for result_path in sorted(
        output_root.glob("repeatability-*-r*/wheel_performance.json")
    ):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        target = manifest.get("repeatability_target")
        if not target:
            continue
        candidate = target["candidate"]
        expected[candidate] = int(target["replicates_requested"])
        grouped.setdefault(candidate, []).append(
            {
                "replicate": int(target["replicate"]),
                "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
                "drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "column_strain_proxy": float(result["lane"]["column_strain_proxy"]),
                "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
                "simulation_source_sha256": (
                    result.get("simulation_source_provenance") or {}
                ).get("combined_sha256"),
                "analysis_source_sha256": (
                    result.get("analysis_source_provenance") or {}
                ).get("combined_sha256"),
                "result_json": str(result_path),
            }
        )

    candidates = []
    for candidate, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["replicate"])
        candidates.append(
            {
                "candidate": candidate,
                "completed_replicates": len(rows),
                "expected_replicates": expected[candidate],
                "torque_nm": variation([row["torque_nm"] for row in rows]),
                "drawbar_to_normal": variation(
                    [row["drawbar_to_normal"] for row in rows]
                ),
                "column_strain_proxy": variation(
                    [row["column_strain_proxy"] for row in rows]
                ),
                "settlement_m": variation([row["settlement_m"] for row in rows]),
                "simulation_source_hashes": sorted(
                    {
                        row["simulation_source_sha256"]
                        for row in rows
                        if row["simulation_source_sha256"]
                    }
                ),
                "analysis_source_hashes": sorted(
                    {
                        row["analysis_source_sha256"]
                        for row in rows
                        if row["analysis_source_sha256"]
                    }
                ),
                "replicates": rows,
            }
        )
    complete = bool(candidates) and all(
        row["completed_replicates"] == row["expected_replicates"]
        for row in candidates
    )
    return {
        "schema_version": 1,
        "status": "COMPLETE" if complete else "PARTIAL",
        "evidence_role": "same_bed_numerical_repeatability",
        "qualification": (
            "Variability here is numerical run-to-run spread on one fixed coarse bed. "
            "Bed-preparation uncertainty requires separate seed and physical repeats."
        ),
        "candidates": candidates,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = []
    for candidate in result["candidates"]:
        rows.append(
            {
                "candidate": candidate["candidate"],
                "completed_replicates": candidate["completed_replicates"],
                "torque_cv": candidate["torque_nm"]["coefficient_of_variation"],
                "drawbar_cv": candidate["drawbar_to_normal"][
                    "coefficient_of_variation"
                ],
                "column_strain_range": candidate["column_strain_proxy"]["range"],
                "settlement_range_m": candidate["settlement_m"]["range"],
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
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    for row in result["candidates"]:
        print(
            f"{row['candidate']}: torque CV="
            f"{row['torque_nm']['coefficient_of_variation']}, "
            f"strain range={row['column_strain_proxy']['range']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
