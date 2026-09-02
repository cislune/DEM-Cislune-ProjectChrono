#!/usr/bin/env python3
"""Summarize completion and runtime for a solver-stall triage queue."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


def _last_match(pattern: str, text: str, cast):
    matches = re.findall(pattern, text)
    return cast(matches[-1]) if matches else None


def evaluate(output_root: Path, queue_path: Path) -> dict:
    project_root = queue_path.resolve().parents[2]
    queue = json.loads(queue_path.read_text())
    rows = []
    for value in queue["manifests"]:
        manifest = json.loads((project_root / value).read_text())
        case_id = manifest["case_id"]
        profile = manifest["solver_stall_triage"]["execution_profile"]
        logs = sorted((output_root / "_logs").glob(f"*_{case_id}_all.log"))
        log_path = logs[-1] if logs else None
        log_text = log_path.read_text(errors="replace") if log_path else ""
        performance_path = output_root / case_id / "wheel_performance.json"
        completed = performance_path.is_file()
        rows.append(
            {
                "execution_profile": profile,
                "case_id": case_id,
                "completed": completed,
                "container_exit_status": _last_match(
                    r"container_exit_status=(\d+)", log_text, int
                ),
                "wall_duration_s": _last_match(
                    r"wall_duration_s=(\d+)", log_text, int
                ),
                "last_wheel_frame": _last_match(
                    r"Wheel frame: (\d+), simulated:", log_text, int
                ),
                "last_simulated_time_s": _last_match(
                    r"Wheel frame: \d+, simulated: ([0-9.eE+-]+) s",
                    log_text,
                    float,
                ),
                "solver_overrides": manifest["solver_stall_triage"][
                    "solver_overrides"
                ],
                "log_path": str(log_path) if log_path else None,
                "performance_path": str(performance_path) if completed else None,
            }
        )

    completed_rows = [row for row in rows if row["completed"]]
    completed_rows.sort(
        key=lambda row: (
            row["wall_duration_s"] is None,
            row["wall_duration_s"] or float("inf"),
            row["execution_profile"],
        )
    )
    return {
        "schema_version": 1,
        "evidence_role": "solver_stall_execution_profile_diagnostic",
        "status": "ONE_OR_MORE_COMPLETED" if completed_rows else "NO_PROFILE_COMPLETED",
        "fastest_completed_profile": (
            completed_rows[0]["execution_profile"] if completed_rows else None
        ),
        "qualification": (
            "Use this result only to choose a profile for a separate repeatability run. "
            "Completion alone is not a calibration or physical-validation result."
        ),
        "profiles": rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["profiles"]:
        rows = []
        for profile in result["profiles"]:
            row = dict(profile)
            row["solver_overrides"] = json.dumps(
                row["solver_overrides"], sort_keys=True
            )
            rows.append(row)
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve(), args.queue.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
