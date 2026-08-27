#!/usr/bin/env python3
"""Run a bounded CPT or wheel manifest queue through the pinned Docker wrappers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def parse_selection(value: str | None, count: int) -> list[int]:
    if not value:
        return list(range(count))
    result = []
    for item in value.split(","):
        index = int(item.strip()) - 1
        if index < 0 or index >= count:
            raise ValueError(f"Queue index {index + 1} is outside 1..{count}")
        result.append(index)
    return result


def completed(project_root: Path, kind: str, case_id: str, env: dict[str, str]) -> bool:
    if kind == "cpt":
        output_root = Path(
            env.get("GRASP_CPT_OUTPUT_ROOT", str(Path.home() / "grasp-cpt-runs"))
        )
        health = output_root / case_id / "penetration" / "cpt_run_health.json"
    else:
        output_root = Path(
            env.get("GRASP_DEM_OUTPUT_ROOT", str(Path.home() / "grasp-dem-runs"))
        )
        health = output_root / case_id / "wheel_performance.json"
    return health.is_file()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path)
    parser.add_argument("--kind", choices=("cpt", "wheel"), required=True)
    parser.add_argument("--select", help="1-based comma-separated queue entries")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    queue = json.loads(args.queue.read_text())
    manifests = queue["manifests"]
    selection = parse_selection(args.select, len(manifests))
    wrapper = project_root / (
        "run_cpt_case_docker.sh" if args.kind == "cpt" else "run_dem_case_docker.sh"
    )
    env = os.environ.copy()
    outcomes = []
    for index in selection:
        manifest = project_root / manifests[index]
        case_id = json.loads(manifest.read_text())["case_id"]
        if completed(project_root, args.kind, case_id, env) and not args.overwrite:
            print(f"SKIP completed: {case_id}", flush=True)
            outcomes.append({"case_id": case_id, "status": "SKIPPED_COMPLETED"})
            continue
        command = [str(wrapper), str(manifest), "--stage", "all"]
        if args.overwrite:
            command.append("--overwrite")
        print(f"RUN {index + 1}/{len(manifests)}: {case_id}", flush=True)
        started = time.time()
        result = subprocess.run(command, cwd=project_root, env=env)
        outcome = {
            "case_id": case_id,
            "exit_status": result.returncode,
            "elapsed_s": time.time() - started,
        }
        outcomes.append(outcome)
        print(json.dumps(outcome, sort_keys=True), flush=True)
        if result.returncode and not args.continue_on_error:
            break
        if args.kind == "wheel" and result.returncode == 0:
            output_root = Path(
                env.get("GRASP_DEM_OUTPUT_ROOT", str(Path.home() / "grasp-dem-runs"))
            )
            analysis = subprocess.run(
                [
                    str(project_root / "analyze_wheel_performance.py"),
                    str(output_root / case_id),
                ],
                cwd=project_root,
                env=env,
            )
            outcome["analysis_exit_status"] = analysis.returncode

    print(json.dumps(outcomes, indent=2, sort_keys=True))
    return 0 if all(item.get("exit_status", 0) == 0 for item in outcomes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
