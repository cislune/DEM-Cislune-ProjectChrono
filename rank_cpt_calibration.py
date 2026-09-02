#!/usr/bin/env python3
"""Rank completed CPT cases and emit a compact calibration table."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def rank(output_root: Path) -> list[dict]:
    rows = []
    for path in output_root.glob("*/penetration/cpt_run_health.json"):
        result = json.loads(path.read_text())
        calibration = result.get("calibration")
        if not calibration:
            continue
        frozen = json.loads((path.parents[1] / "frozen_case.json").read_text())
        terrain = frozen["terrain"]
        preparation_path = path.parents[1] / "terrain" / "terrain_preparation.json"
        preparation = json.loads(preparation_path.read_text()) if preparation_path.exists() else {}
        target_density = preparation.get("target_bulk_density_kg_m3")
        achieved_density = preparation.get("post_release_bulk_density_kg_m3")
        density_ratio = (
            float(achieved_density) / float(target_density)
            if target_density is not None and achieved_density is not None
            else None
        )
        selection_score = calibration["score_lower_is_better"] + (
            5.0 * abs(math.log(density_ratio)) if density_ratio and density_ratio > 0 else 0.0
        )
        rows.append(
            {
                "case_id": result["case_id"],
                "status": result["status"],
                "score": calibration["score_lower_is_better"],
                "selection_score": selection_score,
                "q100_predicted_kpa": calibration["q_100mm_predicted_kpa"],
                "q100_observed_kpa": calibration["q_100mm_observed_kpa"],
                "q100_ratio": calibration["q_100mm_ratio_predicted_to_observed"],
                "predicted_slope_kpa_per_mm": calibration["predicted_fit_10_to_100mm"]["slope_kpa_per_mm"],
                "observed_slope_kpa_per_mm": calibration["observed_fit_10_to_100mm"]["slope_kpa_per_mm"],
                "post_release_bulk_density_kg_m3": preparation.get("post_release_bulk_density_kg_m3"),
                "bulk_density_ratio": density_ratio,
                "density_gate_status": result.get("density_gate", {}).get("status"),
                "youngs_modulus_pa": terrain["youngs_modulus_pa"],
                "particle_friction": terrain["particle_friction"],
                "rolling_resistance": terrain["rolling_resistance"],
                "cohesion": terrain["cohesion"],
                "particle_radius_m": terrain["base_particle_radius_m"],
                "health_json": str(path),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["density_gate_status"] == "REJECT_DENSITY_MISMATCH",
            row["selection_score"],
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = rank(args.output_root.resolve())
    args.csv_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with args.csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    args.json_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print(f"Ranked {len(rows)} completed case(s)")
    for index, row in enumerate(rows, 1):
        print(
            f"{index}. {row['case_id']}: selection={row['selection_score']:.4f}, "
            f"q100={row['q100_predicted_kpa']:.2f}/{row['q100_observed_kpa']:.2f} kPa"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
