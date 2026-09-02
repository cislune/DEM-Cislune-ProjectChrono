#!/usr/bin/env python3
"""Run and resume the GRASP multi-day DEM refinement campaign."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from evaluate_alabama_lap_sequence import evaluate as evaluate_alabama
from evaluate_alabama_lap_sequence import write as write_alabama
from evaluate_candidate_lap_sequences import evaluate as evaluate_candidates
from evaluate_candidate_lap_sequences import write as write_candidates


def available_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024**3)


def project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def write_status(path: Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")


def run_queue(
    project_root: Path,
    queue_path: Path,
    output_root: Path,
    max_wall_s: int,
) -> tuple[int, float]:
    command = [
        sys.executable,
        str(project_root / "run_case_queue.py"),
        str(queue_path),
        "--kind",
        "wheel",
        "--stage",
        "all",
        "--continue-on-error",
        "--max-wall-s",
        str(max_wall_s),
    ]
    environment = dict(__import__("os").environ)
    environment["GRASP_DEM_OUTPUT_ROOT"] = str(output_root)
    started = time.time()
    result = subprocess.run(command, cwd=project_root, env=environment)
    return result.returncode, time.time() - started


def summarize_sensitivity(results_dir: Path) -> None:
    rows = []
    for path in sorted(results_dir.glob("sensitivity-*.json")):
        if path.name == "sensitivity-summary.json":
            continue
        result = json.loads(path.read_text())
        calibration = result.get("summaries", {}).get("calibration", {})
        held_out = result.get("summaries", {}).get("held_out_validation", {})
        rows.append(
            {
                "scenario": path.stem.removeprefix("sensitivity-"),
                "status": result.get("status"),
                "completed_laps": len(result.get("completed_laps", [])),
                "calibration_relative_error": calibration.get("relative_error"),
                "held_out_relative_error": held_out.get("relative_error"),
                "held_out_median_lap_relative_error": held_out.get(
                    "median_lap_relative_error"
                ),
                "held_out_laps_within_20_percent_fraction": held_out.get(
                    "laps_within_20_percent_fraction"
                ),
                "cumulative_density_ratio_proxy": result.get("compaction", {}).get(
                    "simulated_cumulative_column_density_ratio_proxy"
                ),
            }
        )
    summary_json = results_dir / "sensitivity-summary.json"
    summary_json.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    if rows:
        with (results_dir / "sensitivity-summary.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def seed_bed(source: Path, output_root: Path, case_id: str) -> None:
    destination = output_root / case_id
    if destination.is_dir():
        return
    if not source.is_dir():
        raise FileNotFoundError(f"Seed bed case is missing: {source}")
    shutil.copytree(source, destination)
    state = destination / "terrain" / "settled terrain data" / "settled_terrain_data.csv"
    if not state.is_file():
        shutil.rmtree(destination)
        raise FileNotFoundError(f"Copied seed bed lacks settled state: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensitivity-master", type=Path, required=True)
    parser.add_argument("--candidate-master", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed-bed-from", type=Path, required=True)
    parser.add_argument(
        "--seed-bed-case-id",
        default="wheel-shared-bed-r8mm-cpt-informed-process-dt5us-margin0p18",
    )
    parser.add_argument("--max-wall-s", type=int, default=1200)
    parser.add_argument("--minimum-free-gb", type=float, default=20.0)
    parser.add_argument(
        "--section", choices=("all", "sensitivity", "candidates"), default="all"
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results_dir = output_root / "_campaign_results"
    status_path = output_root / "campaign_status.json"
    status = {
        "schema_version": 1,
        "state": "RUNNING",
        "started_epoch": time.time(),
        "output_root": str(output_root),
        "queues": [],
    }
    write_status(status_path, status)
    seed_bed(args.seed_bed_from.resolve(), output_root, args.seed_bed_case_id)

    failures = 0
    if args.section in ("all", "sensitivity"):
        master_path = args.sensitivity_master.resolve()
        master = json.loads(master_path.read_text())
        for value in master["scenario_queues"]:
            if available_gb(output_root) < args.minimum_free_gb:
                status["state"] = "STOPPED_LOW_DISK"
                status["available_gb"] = available_gb(output_root)
                write_status(status_path, status)
                return 3
            queue_path = project_path(project_root, value)
            queue = json.loads(queue_path.read_text())
            scenario = queue["campaign_scenario"]
            print(f"=== SENSITIVITY {scenario} ===", flush=True)
            returncode, elapsed = run_queue(
                project_root, queue_path, output_root, args.max_wall_s
            )
            failures += returncode != 0
            try:
                result = evaluate_alabama(output_root, scenario)
                write_alabama(
                    result,
                    results_dir / f"sensitivity-{scenario}.json",
                    results_dir / f"sensitivity-{scenario}.csv",
                )
                evaluation_status = result["status"]
            except Exception as exc:
                evaluation_status = f"ERROR: {type(exc).__name__}: {exc}"
                failures += 1
            status["queues"].append(
                {
                    "section": "sensitivity",
                    "name": scenario,
                    "returncode": returncode,
                    "elapsed_s": elapsed,
                    "evaluation_status": evaluation_status,
                }
            )
            status["available_gb"] = available_gb(output_root)
            write_status(status_path, status)
            summarize_sensitivity(results_dir)

    if args.section in ("all", "candidates"):
        master_path = args.candidate_master.resolve()
        master = json.loads(master_path.read_text())
        for value in master["candidate_queues"]:
            if available_gb(output_root) < args.minimum_free_gb:
                status["state"] = "STOPPED_LOW_DISK"
                status["available_gb"] = available_gb(output_root)
                write_status(status_path, status)
                return 3
            queue_path = project_path(project_root, value)
            queue = json.loads(queue_path.read_text())
            candidate = queue["candidate"]
            print(f"=== CANDIDATE {candidate} ===", flush=True)
            returncode, elapsed = run_queue(
                project_root, queue_path, output_root, args.max_wall_s
            )
            failures += returncode != 0
            try:
                result = evaluate_candidates(output_root)
                write_candidates(
                    result,
                    results_dir / "candidate-sequence-summary.json",
                    results_dir / "candidate-sequence-summary.csv",
                )
                evaluation_status = result["status"]
            except Exception as exc:
                evaluation_status = f"ERROR: {type(exc).__name__}: {exc}"
                failures += 1
            status["queues"].append(
                {
                    "section": "candidates",
                    "name": candidate,
                    "returncode": returncode,
                    "elapsed_s": elapsed,
                    "evaluation_status": evaluation_status,
                }
            )
            status["available_gb"] = available_gb(output_root)
            write_status(status_path, status)

    status["state"] = "COMPLETE_WITH_FAILURES" if failures else "COMPLETE"
    status["finished_epoch"] = time.time()
    status["failure_count"] = failures
    status["available_gb"] = available_gb(output_root)
    write_status(status_path, status)
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
