#!/usr/bin/env python3
"""Normalize frozen candidate-wheel performance to the smooth control."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def evaluate(output_root: Path) -> dict:
    rows = []
    for result_path in sorted(
        output_root.glob("screen-frozen-*-r8mm/wheel_performance.json")
    ):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        rows.append(
            {
                "candidate": manifest["frozen_screen_provenance"]["candidate"],
                "p95_surface_settlement_m": float(
                    result["lane"]["p95_surface_settlement_m"]
                ),
                "column_strain_proxy": float(result["lane"]["column_strain_proxy"]),
                "median_abs_contact_torque_nm": float(
                    result["mobility"]["torque_y_nm"]["median_abs"]
                ),
                "median_drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "density_gate_status": result["density_gate"]["status"],
                "result_json": str(result_path),
            }
        )
    if not rows:
        raise ValueError(f"No completed frozen candidate cases found in {output_root}")
    smooth = next((row for row in rows if row["candidate"] == "smooth_control"), None)
    if smooth:
        for row in rows:
            row["settlement_vs_smooth"] = (
                row["p95_surface_settlement_m"]
                / smooth["p95_surface_settlement_m"]
            )
            row["strain_vs_smooth"] = (
                row["column_strain_proxy"] / smooth["column_strain_proxy"]
            )
            row["torque_vs_smooth"] = (
                row["median_abs_contact_torque_nm"]
                / smooth["median_abs_contact_torque_nm"]
            )
            row["drawbar_vs_smooth"] = (
                row["median_drawbar_to_normal"]
                / smooth["median_drawbar_to_normal"]
            )
    return {
        "schema_version": 1,
        "status": "COMPLETE" if len(rows) == 3 and smooth else "PARTIAL",
        "qualification": (
            "All cases share frozen parameters and one terrain realization, but the 8 mm bed "
            "fails the physical density gate. Ratios support candidate down-selection only, "
            "not absolute compaction prediction."
        ),
        "candidates": sorted(rows, key=lambda row: row["candidate"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve())
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["candidates"]
    if rows:
        with args.csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    for row in sorted(rows, key=lambda item: item["candidate"]):
        print(
            f"{row['candidate']}: settlement={row.get('settlement_vs_smooth', float('nan')):.3f}x, "
            f"torque={row.get('torque_vs_smooth', float('nan')):.3f}x, "
            f"drawbar={row.get('drawbar_vs_smooth', float('nan')):.3f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
