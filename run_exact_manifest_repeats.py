#!/usr/bin/env python3
"""Run one immutable DEM manifest repeatedly in isolated output roots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def variation(values: list[float]) -> dict:
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "sample_standard_deviation": stdev,
        "coefficient_of_variation": stdev / abs(mean) if abs(mean) > 1e-12 else None,
    }


def link_seed_state(manifest: dict, seed_case: Path, repeat_root: Path) -> dict:
    terrain = manifest["terrain"]
    relative = Path(terrain["initial_state_relative_path"])
    source = seed_case / relative
    if not source.is_file():
        raise FileNotFoundError(f"Seed state not found: {source}")
    target = repeat_root / terrain["initial_state_case_id"] / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)
    if target.exists():
        if sha256_file(target) != source_hash:
            raise RuntimeError(f"Existing seed state hash mismatch: {target}")
    else:
        try:
            os.link(source, target)
        except OSError:
            target.write_bytes(source.read_bytes())
    return {
        "source_path": str(source),
        "source_sha256": source_hash,
        "linked_path": str(target),
        "linked_sha256": sha256_file(target),
    }


def wheel_run_complete(case_dir: Path, manifest: dict) -> bool:
    expected = len(manifest["test"]["slip_ratios"]) * int(
        manifest["test"].get("passes", 1)
    )
    final_states = list(case_dir.glob("wheel/**/settled data/*.csv"))
    return len(final_states) >= expected


def analyze_completed_run(project_root: Path, case_dir: Path, manifest: dict) -> None:
    if not wheel_run_complete(case_dir, manifest):
        return
    subprocess.run(
        [sys.executable, str(project_root / "analyze_wheel_performance.py"), str(case_dir)],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        check=False,
    )


def load_prior_rows(summary_path: Path, manifest_path: Path) -> list[dict]:
    if not summary_path.is_file():
        return []
    prior = json.loads(summary_path.read_text())
    expected_hash = sha256_file(manifest_path)
    if prior.get("manifest_sha256") != expected_hash:
        raise RuntimeError(
            f"Existing repeat summary manifest hash mismatch: {summary_path}"
        )
    rows = prior.get("repeats", [])
    attempts = [
        int(row["attempt"] if "attempt" in row else row["repeat"]) for row in rows
    ]
    if len(attempts) != len(set(attempts)):
        raise RuntimeError(f"Duplicate attempt IDs in repeat summary: {summary_path}")
    return rows


def summarize(
    manifest_path: Path,
    output_root: Path,
    rows: list[dict],
    repeats: int,
    torque_cv_limit: float,
    strain_range_limit: float,
    max_attempts: int | None = None,
) -> dict:
    completed = [row for row in rows if row.get("completed")]
    torque = variation([row["torque_nm"] for row in completed]) if completed else None
    strain = variation([row["column_strain_proxy"] for row in completed]) if completed else None
    complete = len(completed) >= repeats
    checks = {
        "torque_cv": {
            "maximum": torque_cv_limit,
            "value": torque["coefficient_of_variation"] if torque else None,
            "pass": bool(
                torque
                and torque["coefficient_of_variation"] is not None
                and torque["coefficient_of_variation"] <= torque_cv_limit
            ),
        },
        "column_strain_range": {
            "maximum": strain_range_limit,
            "value": strain["range"] if strain else None,
            "pass": bool(strain and strain["range"] <= strain_range_limit),
        },
    }
    status = (
        "PARTIAL"
        if not complete
        else "PASS_PROVISIONAL"
        if all(check["pass"] for check in checks.values())
        else "REJECT_QUALITY_GATE"
    )
    return {
        "schema_version": 1,
        "status": status,
        "evidence_role": "exact_manifest_short_solver_determinism_probe",
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "output_root": str(output_root),
        "repeats_requested": repeats,
        "completed_repeats": len(completed),
        "attempts_allowed": max_attempts if max_attempts is not None else repeats,
        "attempts_recorded": len(rows),
        "torque_nm": torque,
        "column_strain_proxy": strain,
        "quality_gate": checks,
        "qualification": (
            "This short same-state diagnostic isolates numerical execution spread; it is "
            "not a physical calibration or a full-duration wheel-performance result."
        ),
        "repeats": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--seed-case", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--max-attempts",
        type=int,
        help="Maximum launches allowed to obtain the requested successful repeats",
    )
    parser.add_argument("--max-wall-s", type=int, default=1200)
    parser.add_argument("--torque-cv-limit", type=float, default=0.15)
    parser.add_argument("--column-strain-range-limit", type=float, default=0.03)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2")
    max_attempts = args.max_attempts or args.repeats
    if max_attempts < args.repeats:
        parser.error("--max-attempts must be at least --repeats")

    project_root = Path(__file__).resolve().parent
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    try:
        manifest_rel = manifest_path.relative_to(project_root)
    except ValueError as exc:
        raise SystemExit("manifest must be inside the project checkout") from exc
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    cache_root = (args.cache_root or (output_root / "_cache")).resolve()
    summary_path = output_root / "exact-repeat-summary.json"
    rows = load_prior_rows(summary_path, manifest_path)
    last_attempt = max(
        (
            int(row["attempt"] if "attempt" in row else row["repeat"])
            for row in rows
        ),
        default=0,
    )
    summary = summarize(
        manifest_path,
        output_root,
        rows,
        args.repeats,
        args.torque_cv_limit,
        args.column_strain_range_limit,
        max_attempts,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    for attempt in range(last_attempt + 1, max_attempts + 1):
        if summary["completed_repeats"] >= args.repeats:
            break
        repeat_root = output_root / f"r{attempt:02d}"
        seed = link_seed_state(manifest, args.seed_case.resolve(), repeat_root)
        case_dir = repeat_root / manifest["case_id"]
        result_path = case_dir / "wheel_performance.json"
        return_code = 0
        wall_duration_s = None
        if not result_path.is_file():
            analyze_completed_run(project_root, case_dir, manifest)
        if not result_path.is_file():
            env = os.environ.copy()
            env.update(
                {
                    "GRASP_DEM_OUTPUT_ROOT": str(repeat_root),
                    "GRASP_DEM_CACHE_ROOT": str(cache_root),
                    "GRASP_DEM_MAX_WALL_S": str(args.max_wall_s),
                }
            )
            started = time.monotonic()
            return_code = subprocess.run(
                [
                    str(project_root / "run_dem_case_docker.sh"),
                    str(manifest_rel),
                    "--stage",
                    "all",
                    "--overwrite",
                ],
                cwd=project_root,
                env=env,
                check=False,
            ).returncode
            wall_duration_s = time.monotonic() - started
            analyze_completed_run(project_root, case_dir, manifest)
        row = {
            "attempt": attempt,
            "repeat": attempt,
            "completed": result_path.is_file(),
            "container_return_code": return_code,
            "wall_duration_s": wall_duration_s,
            "result_json": str(result_path),
            "seed_state": seed,
        }
        if result_path.is_file():
            result = json.loads(result_path.read_text())
            row.update(
                {
                    "case_id": result["case_id"],
                    "project_git_revision": result.get("project_git_revision"),
                    "simulation_source_sha256": (
                        result.get("simulation_source_provenance") or {}
                    ).get("combined_sha256"),
                    "solver_execution": result.get("solver_execution"),
                    "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
                    "column_strain_proxy": float(result["lane"]["column_strain_proxy"]),
                    "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
                    "drawbar_to_normal": float(
                        result["mobility"]["median_abs_drawbar_over_normal_load"]
                    ),
                }
            )
        rows.append(row)
        summary = summarize(
            manifest_path,
            output_root,
            rows,
            args.repeats,
            args.torque_cv_limit,
            args.column_strain_range_limit,
            max_attempts,
        )
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["completed_repeats"] >= args.repeats else 1


if __name__ == "__main__":
    raise SystemExit(main())
