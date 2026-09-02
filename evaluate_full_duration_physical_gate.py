#!/usr/bin/env python3
"""Evaluate full-duration Alabama repeats against the RIDER torque upper bound."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(summary: dict, manifest: dict, upper_bound_tolerance: float = 0.20) -> dict:
    reference = float(
        manifest["sequence_condition"][
            "measured_steady_tare_corrected_median_abs_torque_nm"
        ]
    )
    torque = summary.get("torque_nm") or {}
    predicted = torque.get("median")
    ratio = predicted / reference if predicted is not None and reference > 0 else None
    if ratio is None:
        physical_status = "PARTIAL"
    elif ratio > 1 + upper_bound_tolerance:
        physical_status = "EXCEEDS_PHYSICAL_UPPER_BOUND"
    elif ratio >= 1 - upper_bound_tolerance:
        physical_status = "WITHIN_20_PERCENT_OF_PHYSICAL_UPPER_BOUND"
    else:
        physical_status = "BELOW_PHYSICAL_UPPER_BOUND_NOT_DISPROVEN"

    if summary.get("status") != "PASS_PROVISIONAL":
        status = "REJECT_NUMERICAL_REPEATABILITY"
    elif physical_status == "EXCEEDS_PHYSICAL_UPPER_BOUND":
        status = "REJECT_EXCEEDS_PHYSICAL_UPPER_BOUND"
    elif predicted is None:
        status = "PARTIAL"
    else:
        status = "PASS_PROVISIONAL_PLAUSIBILITY"

    return {
        "schema_version": 1,
        "status": status,
        "numerical_repeatability_status": summary.get("status"),
        "physical_plausibility_status": physical_status,
        "predicted_median_abs_contact_torque_nm": predicted,
        "predicted_minimum_nm": torque.get("minimum"),
        "predicted_maximum_nm": torque.get("maximum"),
        "rider_steady_tare_corrected_upper_bound_nm": reference,
        "predicted_to_upper_bound_ratio": ratio,
        "upper_bound_tolerance_fraction": upper_bound_tolerance,
        "decision": (
            "Proceed to controlled candidate screening, while retaining provisional physical "
            "calibration status."
            if status == "PASS_PROVISIONAL_PLAUSIBILITY"
            else "Do not resume candidate ranking from this solver profile."
        ),
        "qualification": (
            "The RIDER value retains dynamic rig and drivetrain losses and is therefore an "
            "upper bound on wheel-soil contact torque. A DEM prediction below that value is "
            "not disproven, but does not by itself establish calibrated accuracy."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repeat_summary", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upper-bound-tolerance", type=float, default=0.20)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.repeat_summary.read_text()),
        json.loads(args.manifest.read_text()),
        upper_bound_tolerance=args.upper_bound_tolerance,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    print(result["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
