#!/usr/bin/env python3
"""Compare numerical spread between two same-bed DEM execution profiles."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def relative_change(reference: float | None, comparison: float | None) -> float | None:
    if reference is None or comparison is None or abs(reference) <= 1e-12:
        return None
    return (comparison - reference) / abs(reference)


def _single_profile(summary: dict, label: str) -> str:
    profiles = summary.get("execution_profiles") or []
    if len(profiles) != 1:
        raise ValueError(f"{label} summary must contain exactly one execution profile")
    return profiles[0]


def compare(reference: dict, comparison: dict) -> dict:
    reference_profile = _single_profile(reference, "Reference")
    comparison_profile = _single_profile(comparison, "Comparison")
    if reference_profile == comparison_profile:
        raise ValueError("Execution profiles must be different")

    reference_rows = {row["candidate"]: row for row in reference["candidates"]}
    comparison_rows = {row["candidate"]: row for row in comparison["candidates"]}
    candidate_names = sorted(set(reference_rows) | set(comparison_rows))
    issues = []
    if set(reference_rows) != set(comparison_rows):
        issues.append("MISMATCHED_CANDIDATES")
    if reference.get("status") == "PARTIAL":
        issues.append("REFERENCE_PARTIAL")
    if comparison.get("status") == "PARTIAL":
        issues.append("COMPARISON_PARTIAL")

    candidates = []
    for candidate in candidate_names:
        if candidate not in reference_rows or candidate not in comparison_rows:
            continue
        first = reference_rows[candidate]
        second = comparison_rows[candidate]
        first_torque = first["torque_nm"]["coefficient_of_variation"]
        second_torque = second["torque_nm"]["coefficient_of_variation"]
        first_strain = first["column_strain_proxy"]["range"]
        second_strain = second["column_strain_proxy"]["range"]
        candidates.append(
            {
                "candidate": candidate,
                "reference_torque_cv": first_torque,
                "comparison_torque_cv": second_torque,
                "torque_cv_relative_change": relative_change(
                    first_torque, second_torque
                ),
                "reference_column_strain_range": first_strain,
                "comparison_column_strain_range": second_strain,
                "column_strain_range_relative_change": relative_change(
                    first_strain, second_strain
                ),
                "reference_quality_gate": first["quality_gate"]["status"],
                "comparison_quality_gate": second["quality_gate"]["status"],
            }
        )

    comparable = not issues and bool(candidates)
    torque_changes = [
        row["torque_cv_relative_change"]
        for row in candidates
        if row["torque_cv_relative_change"] is not None
    ]
    strain_changes = [
        row["column_strain_range_relative_change"]
        for row in candidates
        if row["column_strain_range_relative_change"] is not None
    ]
    if (
        not comparable
        or len(torque_changes) != len(candidates)
        or len(strain_changes) != len(candidates)
    ):
        finding = "INCONCLUSIVE"
    elif all(change < 0 for change in torque_changes) and all(
        change <= 0 for change in strain_changes
    ):
        finding = "COMPARISON_PROFILE_LOWER_SPREAD"
    elif all(change >= 0 for change in torque_changes) and all(
        change >= 0 for change in strain_changes
    ):
        finding = "NO_SPREAD_IMPROVEMENT"
    else:
        finding = "MIXED_METRIC_RESPONSE"

    return {
        "schema_version": 1,
        "evidence_role": "solver_execution_profile_repeatability_comparison",
        "status": "COMPLETE" if comparable else "INCONCLUSIVE",
        "finding": finding,
        "reference_profile": reference_profile,
        "comparison_profile": comparison_profile,
        "issues": issues,
        "qualification": (
            "This comparison isolates numerical run-to-run spread on one frozen bed. "
            "A favorable result does not establish physical accuracy or bed-to-bed robustness."
        ),
        "candidates": candidates,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["candidates"]:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(result["candidates"][0])
            )
            writer.writeheader()
            writer.writerows(result["candidates"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference_summary", type=Path)
    parser.add_argument("comparison_summary", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    args = parser.parse_args()
    result = compare(
        json.loads(args.reference_summary.read_text()),
        json.loads(args.comparison_summary.read_text()),
    )
    write(result, args.json_path, args.csv_path)
    print(result["finding"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
