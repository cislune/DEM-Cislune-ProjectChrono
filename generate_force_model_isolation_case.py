#!/usr/bin/env python3
"""Generate a one-variable contact-force-model isolation manifest."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


SUPPORTED_MODELS = {
    "frictional_hertzian",
    "frictionless_hertzian",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(source_path: Path, contact_force_model: str) -> dict:
    if contact_force_model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported contact force model: {contact_force_model}")
    source = json.loads(source_path.read_text())
    case = deepcopy(source)
    case["case_id"] = f"{source['case_id']}-{contact_force_model}"
    case["model_status"] = "short_exact_manifest_force_model_isolation_probe"
    case["purpose"] = (
        "Isolate per-contact friction-history effects while holding the wheel, imported "
        "particle state, kinematics, load, and solver execution profile fixed."
    )
    case["solver"]["contact_force_model"] = contact_force_model
    case["force_model_isolation"] = {
        "contact_force_model": contact_force_model,
        "source_case_id": source["case_id"],
        "source_manifest": str(source_path),
        "source_manifest_sha256": sha256_file(source_path),
        "qualification": (
            "Numerical root-cause diagnostic only. A frictionless result cannot be used "
            "as wheel mobility, torque, or physical compaction validation."
        ),
    }
    return case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--contact-force-model", choices=sorted(SUPPORTED_MODELS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = generate(args.source_manifest.resolve(), args.contact_force_model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
