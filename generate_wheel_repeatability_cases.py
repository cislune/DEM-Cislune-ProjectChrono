#!/usr/bin/env python3
"""Generate independent same-bed repeats for selected wheel screen cases."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file


DEFAULT_CANDIDATES = ("smooth_control", "broad_wave_12", "chevron_wave_14")


def generate(
    source_queue_path: Path,
    output_dir: Path,
    bed_case_id: str,
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
    replicates: int = 3,
    bed_state_sha256: str | None = None,
    case_prefix: str = "repeatability",
    solver_overrides: dict | None = None,
) -> Path:
    if replicates < 2:
        raise ValueError("Repeatability campaign requires at least two replicates")
    if not case_prefix or any(character.isspace() for character in case_prefix):
        raise ValueError("Case prefix must be non-empty and contain no whitespace")
    solver_overrides = dict(solver_overrides or {})
    source_queue = json.loads(source_queue_path.read_text())
    project_root = source_queue_path.parents[2]
    selected = {}
    for value in source_queue["manifests"]:
        path = project_root / value
        case = json.loads(path.read_text())
        candidate = Path(case["wheel"]["obj"]).stem
        if candidate in candidates:
            selected[candidate] = (path, case)
    missing = sorted(set(candidates) - set(selected))
    if missing:
        raise ValueError(f"Source queue lacks candidates: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for candidate in candidates:
        source_path, source = selected[candidate]
        for replicate in range(1, replicates + 1):
            case = copy.deepcopy(source)
            case_id = f"{case_prefix}-{candidate}-r{replicate:02d}"
            case["case_id"] = case_id
            case["model_status"] = "same_bed_numerical_repeatability_check"
            case["purpose"] = (
                "Quantify run-to-run DEM variability while holding the manifest physics, "
                "wheel geometry, and settled terrain realization fixed."
            )
            case["terrain"]["initial_state_case_id"] = bed_case_id
            case["terrain"]["initial_state_filename"] = "settled_terrain_data.csv"
            case["terrain"].pop("initial_state_relative_path", None)
            case.setdefault("solver", {}).update(solver_overrides)
            case["repeatability_target"] = {
                "candidate": candidate,
                "execution_profile": case_prefix,
                "replicate": replicate,
                "replicates_requested": replicates,
                "source_manifest": str(source_path.relative_to(project_root)),
                "source_manifest_sha256": sha256_file(source_path),
                "shared_bed_case_id": bed_case_id,
                "shared_bed_state_sha256": bed_state_sha256,
                "solver_overrides": solver_overrides,
                "qualification": (
                    "This campaign measures numerical repeatability on one fixed coarse bed; "
                    "it does not measure uncertainty across physical bed preparations."
                ),
            }
            destination = output_dir / f"{case_id}.json"
            destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
            manifests.append(destination)

    queue_path = output_dir / "repeatability_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign": "same-bed numerical repeatability",
                "candidates": list(candidates),
                "execution_profile": case_prefix,
                "replicates_per_candidate": replicates,
                "shared_bed_case_id": bed_case_id,
                "shared_bed_state_sha256": bed_state_sha256,
                "solver_overrides": solver_overrides,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-queue",
        type=Path,
        default=Path(
            "cases/frozen_candidate_screen_mu0p9_r8mm/"
            "frozen_candidate_screen_queue.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/wheel_repeatability_r8mm")
    )
    parser.add_argument("--bed-case-id", required=True)
    parser.add_argument("--bed-state-sha256")
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--candidates", nargs="+", default=list(DEFAULT_CANDIDATES))
    parser.add_argument("--case-prefix", default="repeatability")
    parser.add_argument(
        "--use-cub-force-collection",
        action="store_true",
        help="Use DEME CUB force reduction instead of default atomic accumulation.",
    )
    args = parser.parse_args()
    solver_overrides = {}
    if args.use_cub_force_collection:
        solver_overrides = {
            "use_cub_force_collection": True,
            "sort_contact_pairs": True,
        }
    queue = generate(
        args.source_queue.resolve(),
        args.output_dir.resolve(),
        args.bed_case_id,
        tuple(args.candidates),
        args.replicates,
        bed_state_sha256=args.bed_state_sha256,
        case_prefix=args.case_prefix,
        solver_overrides=solver_overrides,
    )
    print(f"Repeatability queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
