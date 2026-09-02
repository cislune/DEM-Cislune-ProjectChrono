#!/usr/bin/env python3
"""Classify exact-repeat launch logs without treating setup errors as solver stalls."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


EXIT_PATTERN = re.compile(r"^container_exit_status=(\d+)$", re.MULTILINE)
FRAME_PATTERN = re.compile(r"Wheel frame: (\d+)")
START_PATTERN = re.compile(r"^run_started_utc=(.+)$", re.MULTILINE)


def classify_log(path: Path) -> dict:
    text = path.read_text(errors="replace")
    status_matches = EXIT_PATTERN.findall(text)
    status = int(status_matches[-1]) if status_matches else None
    frames = [int(value) for value in FRAME_PATTERN.findall(text)]
    preflight_pass = "Preflight: PASS" in text
    if status is None:
        classification = "INCOMPLETE_LOG"
    elif status == 0 and preflight_pass:
        classification = "SUCCESS"
    elif not preflight_pass:
        classification = "SETUP_REJECTED"
    elif status == 124:
        classification = "SOLVER_TIMEOUT"
    elif frames:
        classification = "SOLVER_TERMINATED_AFTER_START"
    else:
        classification = "INTERRUPTED_BEFORE_SOLVER_PROGRESS"
    start_matches = START_PATTERN.findall(text)
    return {
        "log_path": str(path),
        "run_started_utc": start_matches[-1] if start_matches else None,
        "preflight_pass": preflight_pass,
        "container_exit_status": status,
        "maximum_wheel_frame": max(frames) if frames else None,
        "classification": classification,
    }


def summarize(root: Path) -> dict:
    profiles = []
    all_rows = []
    for profile_root in sorted(path for path in root.iterdir() if path.is_dir()):
        rows = [
            classify_log(path)
            for path in sorted(profile_root.glob("r*/_logs/*_all.log"))
        ]
        if not rows:
            continue
        for row in rows:
            row["profile"] = profile_root.name
        counts = {}
        for row in rows:
            counts[row["classification"]] = counts.get(row["classification"], 0) + 1
        failed_solver_launches = counts.get("SOLVER_TIMEOUT", 0) + counts.get(
            "SOLVER_TERMINATED_AFTER_START", 0
        )
        profiles.append(
            {
                "profile": profile_root.name,
                "successful_launches": counts.get("SUCCESS", 0),
                "failed_solver_launches": failed_solver_launches,
                "setup_rejections": counts.get("SETUP_REJECTED", 0),
                "interrupted_before_solver_progress": counts.get(
                    "INTERRUPTED_BEFORE_SOLVER_PROGRESS", 0
                ),
                "incomplete_logs": counts.get("INCOMPLETE_LOG", 0),
            }
        )
        all_rows.extend(rows)
    return {
        "schema_version": 1,
        "evidence_role": "solver_launch_reliability",
        "qualification": (
            "Only preflight-passing timeouts or terminations after a wheel frame are counted "
            "as failed solver launches. Setup rejections and pre-progress operator/service "
            "interruptions are reported separately."
        ),
        "profiles": profiles,
        "launches": all_rows,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["launches"]
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = summarize(args.root.resolve())
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    for row in result["profiles"]:
        print(
            f"{row['profile']}: {row['successful_launches']} success, "
            f"{row['failed_solver_launches']} solver failure"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
