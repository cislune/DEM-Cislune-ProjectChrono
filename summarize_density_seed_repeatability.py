#!/usr/bin/env python3
"""Summarize selected-margin bed density across independent seeds."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def preparation_row(path: Path) -> dict:
    preparation = json.loads(path.read_text())
    case = json.loads((path.parent.parent / "frozen_case.json").read_text())
    achieved = float(preparation["post_release_bulk_density_kg_m3"])
    target = float(preparation["target_bulk_density_kg_m3"])
    return {
        "case_id": case["case_id"],
        "random_seed": int(case["terrain"].get("random_seed", 77)),
        "compression_release_margin": float(
            case["terrain"]["compression_release_margin"]
        ),
        "target_bulk_density_kg_m3": target,
        "post_release_bulk_density_kg_m3": achieved,
        "achieved_to_target_ratio": achieved / target,
    }


def summarize(paths: list[Path], tolerance_fraction: float = 0.03) -> dict:
    if len(paths) < 2:
        raise ValueError("At least two completed density preparations are required")
    rows = [preparation_row(path) for path in paths]
    margins = {row["compression_release_margin"] for row in rows}
    targets = {row["target_bulk_density_kg_m3"] for row in rows}
    if len(margins) != 1 or len(targets) != 1:
        raise ValueError("Density repeats must share one margin and target")
    achieved = [row["post_release_bulk_density_kg_m3"] for row in rows]
    target = rows[0]["target_bulk_density_kg_m3"]
    mean = statistics.mean(achieved)
    standard_deviation = statistics.stdev(achieved)
    cv = standard_deviation / mean if mean else None
    all_within = all(
        abs(row["achieved_to_target_ratio"] - 1) <= tolerance_fraction
        for row in rows
    )
    repeatable = cv is not None and cv <= tolerance_fraction
    if all_within and repeatable:
        status = "PASS_DENSITY_TARGET_AND_REPEATABILITY"
    elif repeatable:
        status = "PASS_REPEATABILITY_REJECT_TARGET"
    else:
        status = "REJECT_DENSITY_REPEATABILITY"
    return {
        "schema_version": 1,
        "status": status,
        "target_bulk_density_kg_m3": target,
        "compression_release_margin": rows[0]["compression_release_margin"],
        "tolerance_fraction": tolerance_fraction,
        "post_release_density_kg_m3": {
            "minimum": min(achieved),
            "maximum": max(achieved),
            "mean": mean,
            "sample_standard_deviation": standard_deviation,
            "coefficient_of_variation": cv,
        },
        "all_seeds_within_target_tolerance": all_within,
        "repeatability_within_tolerance": repeatable,
        "preparations": rows,
        "decision": (
            "Use this preparation for a finer wheel validation bed."
            if status == "PASS_DENSITY_TARGET_AND_REPEATABILITY"
            else "Do not use this preparation for absolute wheel compaction prediction."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preparations", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-fraction", type=float, default=0.03)
    args = parser.parse_args()
    result = summarize(
        [path.resolve() for path in args.preparations],
        args.tolerance_fraction,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    print(result["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
