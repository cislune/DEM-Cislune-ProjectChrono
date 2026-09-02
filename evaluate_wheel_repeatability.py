#!/usr/bin/env python3
"""Summarize same-bed numerical variability for wheel DEM metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def variation(values: list[float]) -> dict:
    mean = statistics.mean(values)
    standard_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "sample_standard_deviation": standard_deviation,
        "coefficient_of_variation": (
            standard_deviation / abs(mean) if abs(mean) > 1e-12 else None
        ),
    }


def evaluate(
    output_root: Path,
    torque_cv_limit: float = 0.15,
    column_strain_range_limit: float = 0.03,
) -> dict:
    grouped: dict[str, list[dict]] = {}
    expected = {}
    for result_path in sorted(output_root.glob("*-r*/wheel_performance.json")):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        target = manifest.get("repeatability_target")
        if not target:
            continue
        candidate = target["candidate"]
        expected[candidate] = int(target["replicates_requested"])
        grouped.setdefault(candidate, []).append(
            {
                "execution_profile": target.get(
                    "execution_profile", "repeatability"
                ),
                "replicate": int(target["replicate"]),
                "torque_nm": float(result["mobility"]["torque_y_nm"]["median_abs"]),
                "drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "column_strain_proxy": float(result["lane"]["column_strain_proxy"]),
                "settlement_m": float(result["lane"]["p95_surface_settlement_m"]),
                "simulation_source_sha256": (
                    result.get("simulation_source_provenance") or {}
                ).get("combined_sha256"),
                "analysis_source_sha256": (
                    result.get("analysis_source_provenance") or {}
                ).get("combined_sha256"),
                "project_git_revision": result.get("project_git_revision"),
                "project_git_dirty": result.get("project_git_dirty"),
                "shared_bed_state_sha256": target.get("shared_bed_state_sha256"),
                "result_json": str(result_path),
            }
        )

    candidates = []
    campaign_issues = []
    for candidate, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["replicate"])
        replicate_numbers = [row["replicate"] for row in rows]
        simulation_hashes = sorted(
            {
                row["simulation_source_sha256"]
                for row in rows
                if row["simulation_source_sha256"]
            }
        )
        analysis_hashes = sorted(
            {
                row["analysis_source_sha256"]
                for row in rows
                if row["analysis_source_sha256"]
            }
        )
        bed_hashes = sorted(
            {
                row["shared_bed_state_sha256"]
                for row in rows
                if row["shared_bed_state_sha256"]
            }
        )
        revisions = sorted(
            {row["project_git_revision"] for row in rows if row["project_git_revision"]}
        )
        execution_profiles = sorted({row["execution_profile"] for row in rows})
        issues = []
        if len(replicate_numbers) != len(set(replicate_numbers)):
            issues.append("DUPLICATE_REPLICATE_NUMBER")
        if any(row["simulation_source_sha256"] is None for row in rows):
            issues.append("MISSING_SIMULATION_SOURCE_PROVENANCE")
        if len(simulation_hashes) > 1:
            issues.append("MIXED_SIMULATION_SOURCE_PROVENANCE")
        if any(row["analysis_source_sha256"] is None for row in rows):
            issues.append("MISSING_ANALYSIS_SOURCE_PROVENANCE")
        if len(analysis_hashes) > 1:
            issues.append("MIXED_ANALYSIS_SOURCE_PROVENANCE")
        if any(row["shared_bed_state_sha256"] is None for row in rows):
            issues.append("MISSING_SHARED_BED_HASH")
        if len(bed_hashes) > 1:
            issues.append("MIXED_SHARED_BED_HASH")
        if any(row["project_git_dirty"] is True for row in rows):
            issues.append("DIRTY_PROJECT_SOURCE")
        if len(execution_profiles) > 1:
            issues.append("MIXED_EXECUTION_PROFILE")

        torque = variation([row["torque_nm"] for row in rows])
        column_strain = variation([row["column_strain_proxy"] for row in rows])
        numerical_checks = {
            "torque_cv": {
                "value": torque["coefficient_of_variation"],
                "maximum": torque_cv_limit,
                "pass": (
                    torque["coefficient_of_variation"] is not None
                    and torque["coefficient_of_variation"] <= torque_cv_limit
                ),
            },
            "column_strain_range": {
                "value": column_strain["range"],
                "maximum": column_strain_range_limit,
                "pass": column_strain["range"] <= column_strain_range_limit,
            },
        }
        complete_replicates = replicate_numbers == list(
            range(1, expected[candidate] + 1)
        )
        if not complete_replicates:
            issues.append("INCOMPLETE_REPLICATES")
        if complete_replicates and not all(
            check["pass"] for check in numerical_checks.values()
        ):
            issues.append("NUMERICAL_REPEATABILITY_LIMIT_EXCEEDED")
        campaign_issues.extend(f"{candidate}:{issue}" for issue in issues)
        candidates.append(
            {
                "candidate": candidate,
                "completed_replicates": len(rows),
                "expected_replicates": expected[candidate],
                "replicate_numbers": replicate_numbers,
                "torque_nm": torque,
                "drawbar_to_normal": variation(
                    [row["drawbar_to_normal"] for row in rows]
                ),
                "column_strain_proxy": column_strain,
                "settlement_m": variation([row["settlement_m"] for row in rows]),
                "simulation_source_hashes": simulation_hashes,
                "analysis_source_hashes": analysis_hashes,
                "project_git_revisions": revisions,
                "execution_profiles": execution_profiles,
                "shared_bed_state_hashes": bed_hashes,
                "quality_gate": {
                    "status": "PASS_PROVISIONAL" if not issues else "REJECT",
                    "issues": issues,
                    "numerical_checks": numerical_checks,
                },
                "replicates": rows,
            }
        )
    complete = bool(candidates) and all(
        row["replicate_numbers"] == list(range(1, row["expected_replicates"] + 1))
        for row in candidates
    )
    status = (
        "PARTIAL"
        if not complete
        else "REJECT_QUALITY_GATE"
        if campaign_issues
        else "PASS_PROVISIONAL"
    )
    return {
        "schema_version": 1,
        "status": status,
        "evidence_role": "same_bed_numerical_repeatability",
        "execution_profiles": sorted(
            {
                profile
                for candidate in candidates
                for profile in candidate["execution_profiles"]
            }
        ),
        "decision_gate": {
            "purpose": (
                "Proceed to wheel ranking and a bounded physical retest only after fixed-bed "
                "numerical variability and source provenance pass."
            ),
            "torque_cv_limit": torque_cv_limit,
            "column_strain_range_limit": column_strain_range_limit,
            "issues": campaign_issues,
        },
        "qualification": (
            "Variability here is numerical run-to-run spread on one fixed coarse bed. "
            "Bed-preparation uncertainty requires separate seed and physical repeats."
        ),
        "candidates": candidates,
    }


def write(result: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = []
    for candidate in result["candidates"]:
        rows.append(
            {
                "candidate": candidate["candidate"],
                "execution_profiles": ";".join(candidate["execution_profiles"]),
                "completed_replicates": candidate["completed_replicates"],
                "torque_cv": candidate["torque_nm"]["coefficient_of_variation"],
                "drawbar_cv": candidate["drawbar_to_normal"][
                    "coefficient_of_variation"
                ],
                "column_strain_range": candidate["column_strain_proxy"]["range"],
                "settlement_range_m": candidate["settlement_m"]["range"],
                "quality_gate_status": candidate["quality_gate"]["status"],
                "quality_gate_issues": ";".join(candidate["quality_gate"]["issues"]),
            }
        )
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    parser.add_argument("--torque-cv-limit", type=float, default=0.15)
    parser.add_argument("--column-strain-range-limit", type=float, default=0.03)
    args = parser.parse_args()
    result = evaluate(
        args.output_root.resolve(),
        args.torque_cv_limit,
        args.column_strain_range_limit,
    )
    write(result, args.json_path.resolve(), args.csv_path.resolve())
    print(result["status"])
    for row in result["candidates"]:
        print(
            f"{row['candidate']}: torque CV="
            f"{row['torque_nm']['coefficient_of_variation']}, "
            f"strain range={row['column_strain_proxy']['range']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
