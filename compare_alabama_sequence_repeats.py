#!/usr/bin/env python3
"""Compare two Alabama repeated-traffic sequences lap by lap."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def load_sequence(root: Path, scenario: str | None) -> dict[int, dict]:
    rows = {}
    for result_path in sorted(root.glob("*/wheel_performance.json")):
        manifest_path = result_path.parent / "frozen_case.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        condition = manifest.get("sequence_condition")
        if not condition:
            continue
        if scenario is not None and condition.get("campaign_scenario") != scenario:
            continue
        result = json.loads(result_path.read_text())
        lap = int(condition["lap"])
        rows[lap] = {
            "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
            "drawbar_to_normal": float(
                result["mobility"]["median_abs_drawbar_over_normal_load"]
            ),
            "column_strain_proxy": float(result["lane"]["column_strain_proxy"]),
            "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
            "shared_bed_state_sha256": condition.get("shared_bed_state_sha256"),
            "simulation_source_sha256": (
                result.get("simulation_source_provenance") or {}
            ).get("combined_sha256"),
            "analysis_source_sha256": (
                result.get("analysis_source_provenance") or {}
            ).get("combined_sha256"),
            "result_json": str(result_path),
        }
    return rows


def relative_delta(value: float, reference: float) -> float | None:
    return abs(value - reference) / abs(reference) if abs(reference) > 1e-12 else None


def symmetric_relative_delta(left: float, right: float) -> float | None:
    scale = abs(left) + abs(right)
    return 2.0 * abs(left - right) / scale if scale > 1e-12 else None


def evaluate(
    first_root: Path,
    second_root: Path,
    first_scenario: str | None = None,
    second_scenario: str | None = None,
) -> dict:
    first = load_sequence(first_root, first_scenario)
    second = load_sequence(second_root, second_scenario)
    matched_laps = sorted(set(first) & set(second))
    if not matched_laps:
        raise ValueError("No matching Alabama sequence laps were found")
    rows = []
    for lap in matched_laps:
        left = first[lap]
        right = second[lap]
        rows.append(
            {
                "lap": lap,
                "first_torque_nm": left["torque_nm"],
                "second_torque_nm": right["torque_nm"],
                "torque_relative_delta_to_first": relative_delta(
                    right["torque_nm"], left["torque_nm"]
                ),
                "torque_symmetric_relative_delta": symmetric_relative_delta(
                    left["torque_nm"], right["torque_nm"]
                ),
                "drawbar_absolute_delta": abs(
                    right["drawbar_to_normal"] - left["drawbar_to_normal"]
                ),
                "column_strain_absolute_delta": abs(
                    right["column_strain_proxy"] - left["column_strain_proxy"]
                ),
                "settlement_absolute_delta_m": abs(
                    right["settlement_m"] - left["settlement_m"]
                ),
                "first_result_json": left["result_json"],
                "second_result_json": right["result_json"],
            }
        )
    bed_hashes = sorted(
        {
            row["shared_bed_state_sha256"]
            for row in list(first.values()) + list(second.values())
            if row["shared_bed_state_sha256"]
        }
    )
    simulation_hashes = sorted(
        {
            row["simulation_source_sha256"]
            for row in list(first.values()) + list(second.values())
            if row["simulation_source_sha256"]
        }
    )
    analysis_hashes = sorted(
        {
            row["analysis_source_sha256"]
            for row in list(first.values()) + list(second.values())
            if row["analysis_source_sha256"]
        }
    )
    complete = matched_laps == list(range(1, 11))
    return {
        "schema_version": 1,
        "status": "COMPLETE_DIAGNOSTIC" if complete else "PARTIAL_DIAGNOSTIC",
        "evidence_role": "same_configuration_repeat_comparison",
        "matched_laps": matched_laps,
        "shared_bed_state_hashes": bed_hashes,
        "shared_bed_match": len(bed_hashes) == 1,
        "simulation_source_hashes": simulation_hashes,
        "analysis_source_hashes": analysis_hashes,
        "source_provenance_complete": all(
            row["simulation_source_sha256"] and row["analysis_source_sha256"]
            for row in list(first.values()) + list(second.values())
        ),
        "summary": {
            "median_torque_relative_delta_to_first": statistics.median(
                row["torque_relative_delta_to_first"]
                for row in rows
                if row["torque_relative_delta_to_first"] is not None
            ),
            "median_torque_symmetric_relative_delta": statistics.median(
                row["torque_symmetric_relative_delta"]
                for row in rows
                if row["torque_symmetric_relative_delta"] is not None
            ),
            "median_column_strain_absolute_delta": statistics.median(
                row["column_strain_absolute_delta"] for row in rows
            ),
            "maximum_column_strain_absolute_delta": max(
                row["column_strain_absolute_delta"] for row in rows
            ),
        },
        "qualification": (
            "This is a diagnostic of repeat-to-repeat spread. Treat it as numerical "
            "variability only when the shared-bed hash and exact source provenance match."
        ),
        "laps": rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result["laps"][0]))
        writer.writeheader()
        writer.writerows(result["laps"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first_root", type=Path)
    parser.add_argument("second_root", type=Path)
    parser.add_argument("--first-scenario")
    parser.add_argument("--second-scenario")
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(
        args.first_root.resolve(),
        args.second_root.resolve(),
        args.first_scenario,
        args.second_scenario,
    )
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
