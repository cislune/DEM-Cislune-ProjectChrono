#!/usr/bin/env python3
"""Generate a one-variable full-duration wheel-friction case."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def friction_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(source_path: Path, wheel_friction: float) -> dict:
    if wheel_friction <= 0:
        raise ValueError("Wheel friction must be positive")
    source = json.loads(source_path.read_text())
    source_friction = float(source["terrain"]["wheel_friction"])
    case = deepcopy(source)
    case["case_id"] = (
        f"{source['case_id']}-wheel-mu{friction_label(wheel_friction)}"
    )
    case["model_status"] = "full_duration_local_wheel_friction_sensitivity"
    case["purpose"] = (
        "Measure one-factor full-duration wheel-friction sensitivity after the selected "
        "solver profile passes numerical repeatability."
    )
    case["terrain"]["wheel_friction"] = wheel_friction
    sequence = case.setdefault("sequence_condition", {})
    sequence["frozen_wheel_friction"] = wheel_friction
    sequence["sensitivity_overrides"] = {"wheel_friction": wheel_friction}
    case["full_duration_friction_sensitivity"] = {
        "source_case_id": source["case_id"],
        "source_manifest": str(source_path),
        "source_manifest_sha256": sha256_file(source_path),
        "source_wheel_friction": source_friction,
        "wheel_friction": wheel_friction,
        "qualification": (
            "Local calibration sensitivity on one imported bed state. A plausible result "
            "must be repeated on a held-out lap or independently prepared bed."
        ),
    }
    return case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--wheel-friction", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = generate(args.source_manifest.resolve(), args.wheel_friction)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
