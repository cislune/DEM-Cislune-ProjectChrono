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
    launch_path = root / "launch-summary.json"
    launch_rows = (
        json.loads(launch_path.read_text()).get("profiles", [])
        if launch_path.is_file()
        else []
    )
    launch_by_profile = {row["profile"]: row for row in launch_rows}
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
        attempts_recorded = summary.get("attempts_recorded", len(summary["repeats"]))
        attempts_allowed = summary.get(
            "attempts_allowed", summary.get("repeats_requested", attempts_recorded)
        )
        launch = launch_by_profile.get(profile, {})
        failed_attempts = launch.get(
            "failed_solver_launches",
            attempts_recorded - summary["completed_repeats"],
        )
        attempts_recorded = max(
            attempts_recorded,
            summary["completed_repeats"] + failed_attempts,
        )
        profiles.append(
            {
                "profile": profile,
                "status": summary["status"],
                "completed_repeats": summary["completed_repeats"],
                "failed_attempts": failed_attempts,
                "attempts_recorded": attempts_recorded,
                "attempts_allowed": attempts_allowed,
                "setup_rejections": launch.get("setup_rejections", 0),
                "interrupted_before_solver_progress": launch.get(
                    "interrupted_before_solver_progress", 0
                ),
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
            "robustness remain separate validation steps. Setup rejections and operator/service "
            "interruptions are excluded from failed solver-launch counts."
        ),
        "launch_summary_json": str(launch_path) if launch_path.is_file() else None,
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
