#!/usr/bin/env python3
"""Generate bounded execution-profile diagnostics from one stalled DEM case."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from dem_case_runner import sha256_file


PROFILES = {
    "cub": {
        "use_cub_force_collection": True,
    },
    "fixed-cd20": {
        "cd_update_frequency": 20,
        "disable_adaptive_update_frequency": True,
    },
    "cub-fixed-cd20": {
        "use_cub_force_collection": True,
        "cd_update_frequency": 20,
        "disable_adaptive_update_frequency": True,
    },
}


def generate(source_manifest: Path, output_dir: Path) -> Path:
    project_root = Path(__file__).resolve().parent
    source_manifest = source_manifest.resolve()
    output_dir = output_dir.resolve()
    source = json.loads(source_manifest.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for profile, overrides in PROFILES.items():
        case = copy.deepcopy(source)
        case_id = f"stall-triage-{profile}-{source['case_id']}"
        case["case_id"] = case_id
        case["model_status"] = "solver_stall_execution_profile_diagnostic"
        case["purpose"] = (
            "Determine whether force reduction or fixed contact-detection update "
            "frequency allows a previously stalled case to complete under the same physics."
        )
        case.setdefault("solver", {}).update(overrides)
        case["solver_stall_triage"] = {
            "execution_profile": profile,
            "solver_overrides": overrides,
            "source_case_id": source["case_id"],
            "source_manifest": str(source_manifest.relative_to(project_root)),
            "source_manifest_sha256": sha256_file(source_manifest),
            "qualification": (
                "Completion is an execution-stability result. It does not establish "
                "physical accuracy or numerical repeatability."
            ),
        }
        destination = output_dir / f"{case_id}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    queue_path = output_dir / "solver_stall_triage_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign": "solver stall execution-profile diagnostic",
                "source_case_id": source["case_id"],
                "seed_case_id": source["terrain"]["initial_state_case_id"],
                "profiles": PROFILES,
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
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    queue = generate(args.source_manifest, args.output_dir)
    print(f"Solver stall triage queue: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
