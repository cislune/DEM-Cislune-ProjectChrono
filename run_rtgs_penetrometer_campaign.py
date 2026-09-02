#!/usr/bin/env python3
"""Run and resume the held-out RTGS CPT trend-validation campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from evaluate_rtgs_penetrometer_sequences import evaluate, write
from run_dem_refinement_campaign import (
    available_gb,
    project_path,
    seed_bed,
    write_status,
)


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed-bed-from", type=Path, required=True)
    parser.add_argument(
        "--seed-bed-case-id",
        default="wheel-shared-bed-r8mm-cpt-informed-process-dt5us-margin0p18",
    )
    parser.add_argument("--max-wall-s", type=int, default=1200)
    parser.add_argument("--minimum-free-gb", type=float, default=20.0)
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
    master_path = args.master.resolve()
    master = json.loads(master_path.read_text())
    for value in master["design_queues"]:
        if available_gb(output_root) < args.minimum_free_gb:
            status["state"] = "STOPPED_LOW_DISK"
            status["available_gb"] = available_gb(output_root)
            write_status(status_path, status)
            return 3
        queue_path = project_path(project_root, value)
        queue = json.loads(queue_path.read_text())
        design = queue["design"]
        print(f"=== RTGS CPT {design} ===", flush=True)
        returncode, elapsed = run_queue(
            project_root, queue_path, output_root, args.max_wall_s
        )
        failures += returncode != 0
        try:
            result = evaluate(output_root, args.reference.resolve())
            write(
                result,
                results_dir / "rtgs-penetrometer-validation.json",
                results_dir / "rtgs-penetrometer-validation.csv",
            )
            evaluation_status = result["status"]
        except Exception as exc:
            evaluation_status = f"ERROR: {type(exc).__name__}: {exc}"
            failures += 1
        status["queues"].append(
            {
                "design": design,
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
