#!/usr/bin/env python3
"""Generate a full-duration exact-repeat case for a selected solver profile."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from generate_solver_determinism_probe_cases import PROFILES


SOLVER_PROFILE_KEYS = {
    key for overrides in PROFILES.values() for key in overrides
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(source_path: Path, profile: str) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"Unsupported solver profile: {profile}")
    source = json.loads(source_path.read_text())
    case = deepcopy(source)
    source_case_id = source["case_id"]
    suffix = source_case_id.removeprefix("repeatability-cub-")
    case["case_id"] = f"repeatability-{profile}-{suffix}"
    case["model_status"] = "same_bed_full_duration_solver_profile_check"
    case["purpose"] = (
        "Verify full-duration numerical repeatability and RIDER torque plausibility using "
        "the solver profile selected by the short exact-manifest gate."
    )
    case["solver"] = deepcopy(case.get("solver", {}))
    for key in SOLVER_PROFILE_KEYS:
        case["solver"].pop(key, None)
    case["solver"].update(PROFILES[profile])
    target = case.setdefault("repeatability_target", {})
    target["execution_profile"] = profile
    target["solver_overrides"] = deepcopy(PROFILES[profile])
    case["full_duration_solver_gate"] = {
        "selected_profile": profile,
        "source_case_id": source_case_id,
        "source_manifest": str(source_path),
        "source_manifest_sha256": sha256_file(source_path),
        "qualification": (
            "Passing numerical repeatability permits physical comparison; it does not by "
            "itself establish absolute prediction accuracy."
        ),
    }
    return case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = generate(args.source_manifest.resolve(), args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
