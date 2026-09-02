#!/usr/bin/env python3
"""Evaluate repeated-traffic candidate sequences relative to the smooth control."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def evaluate(output_root: Path) -> dict:
    grouped: dict[str, list[dict]] = {}
    for result_path in sorted(output_root.glob("candidate-sequence-*-lap*/wheel_performance.json")):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        condition = manifest.get("candidate_sequence")
        if not condition:
            continue
        strain = float(result["lane"]["column_strain_proxy"])
        grouped.setdefault(condition["candidate"], []).append(
            {
                "lap": int(condition["lap"]),
                "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
                "drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
                "density_ratio_increment": 1.0 / (1.0 - strain),
                "density_gate_status": result["density_gate"]["status"],
                "result_json": str(result_path),
            }
        )

    rows = []
    for candidate, laps in grouped.items():
        laps.sort(key=lambda item: item["lap"])
        cumulative_density_ratio = 1.0
        for lap in laps:
            cumulative_density_ratio *= lap["density_ratio_increment"]
        rows.append(
            {
                "candidate": candidate,
                "completed_laps": len(laps),
                "median_contact_torque_nm": statistics.median(
                    lap["torque_nm"] for lap in laps
                ),
                "median_drawbar_to_normal": statistics.median(
                    lap["drawbar_to_normal"] for lap in laps
                ),
                "cumulative_settlement_m": sum(lap["settlement_m"] for lap in laps),
                "cumulative_density_ratio_proxy": cumulative_density_ratio,
                "maximum_incremental_settlement_m": max(
                    lap["settlement_m"] for lap in laps
                ),
                "all_density_gates_pass": all(
                    lap["density_gate_status"] == "PASS_DENSITY" for lap in laps
                ),
            }
        )
    rows.sort(key=lambda item: item["candidate"])
    smooth = next((row for row in rows if row["candidate"] == "smooth_control"), None)
    if smooth:
        for row in rows:
            row["torque_vs_smooth"] = (
                row["median_contact_torque_nm"] / smooth["median_contact_torque_nm"]
            )
            row["drawbar_vs_smooth"] = (
                row["median_drawbar_to_normal"] / smooth["median_drawbar_to_normal"]
            )
            row["settlement_vs_smooth"] = (
                row["cumulative_settlement_m"] / smooth["cumulative_settlement_m"]
            )
            row["density_ratio_gain_vs_smooth"] = (
                (row["cumulative_density_ratio_proxy"] - 1.0)
                / (smooth["cumulative_density_ratio_proxy"] - 1.0)
            )
    complete = bool(rows) and smooth is not None and all(
        row["completed_laps"] == 10 for row in rows
    )
    return {
        "schema_version": 1,
        "status": "COMPLETE" if complete else "PARTIAL",
        "qualification": (
            "Repeated-traffic geometry comparison on the frozen 8 mm pilot bed. "
            "Absolute compaction remains withheld because the physical density gate fails."
        ),
        "candidates": rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["candidates"]
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
            f"{row['candidate']}: settlement={row.get('settlement_vs_smooth', float('nan')):.3f}x, "
            f"torque={row.get('torque_vs_smooth', float('nan')):.3f}x, "
            f"drawbar={row.get('drawbar_vs_smooth', float('nan')):.3f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
