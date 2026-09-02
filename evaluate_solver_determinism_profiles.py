#!/usr/bin/env python3
"""Compare exact-manifest solver determinism profiles."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def evaluate(root: Path) -> dict:
    profiles = []
    for path in sorted(root.glob("*/exact-repeat-summary.json")):
        summary = json.loads(path.read_text())
        torque = summary.get("torque_nm") or {}
        strain = summary.get("column_strain_proxy") or {}
        profile = path.parent.name
        wall_durations = [
            row["wall_duration_s"]
            for row in summary["repeats"]
            if row.get("wall_duration_s") is not None
        ]
        profiles.append(
            {
                "profile": profile,
                "status": summary["status"],
                "completed_repeats": summary["completed_repeats"],
                "torque_cv": torque.get("coefficient_of_variation"),
                "column_strain_range": strain.get("range"),
                "median_wall_duration_s": (
                    statistics.median(wall_durations) if wall_durations else None
                ),
                "summary_json": str(path),
            }
        )
    passing = [row for row in profiles if row["status"] == "PASS_PROVISIONAL"]
    passing.sort(
        key=lambda row: (
            row["torque_cv"] if row["torque_cv"] is not None else float("inf"),
            row["column_strain_range"]
            if row["column_strain_range"] is not None
            else float("inf"),
        )
    )
    return {
        "schema_version": 1,
        "status": "PASS_PROVISIONAL" if passing else "REJECT_QUALITY_GATE",
        "selected_profile": passing[0]["profile"] if passing else None,
        "decision": (
            "Run the selected profile at the full Alabama lap-3 duration before resuming "
            "candidate ranking."
            if passing
            else "Do not resume wheel ranking; isolate friction-history/contact-order behavior."
        ),
        "qualification": (
            "Short exact-manifest execution gate only. Physical calibration and bed-to-bed "
            "robustness remain separate validation steps."
        ),
        "profiles": profiles,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["profiles"]:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(result["profiles"][0]))
            writer.writeheader()
            writer.writerows(result["profiles"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.root.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    for row in result["profiles"]:
        print(
            f"{row['profile']}: {row['status']}, torque CV={row['torque_cv']}, "
            f"strain range={row['column_strain_range']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
