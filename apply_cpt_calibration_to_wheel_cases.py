#!/usr/bin/env python3
"""Create CPT-informed wheel cases without overwriting the source manifests."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from cpt_reference import sha256_file


MATERIAL_KEYS = (
    "youngs_modulus_pa",
    "particle_friction",
    "rolling_resistance",
    "cohesion",
)


class CalibrationSelectionError(ValueError):
    pass


def select_calibration(rank_path: Path, allow_density_reject: bool = False) -> dict:
    rows = json.loads(rank_path.read_text())
    if not isinstance(rows, list) or not rows:
        raise CalibrationSelectionError(f"No ranked CPT cases in {rank_path}")
    for row in rows:
        if allow_density_reject or row.get("density_gate_status") != "REJECT_DENSITY_MISMATCH":
            return row
    raise CalibrationSelectionError(
        "No CPT case passed the density gate; do not transfer a force fit from a mismatched bed"
    )


def create_cases(
    queue_path: Path,
    rank_path: Path,
    output_dir: Path,
    allow_density_reject: bool = False,
) -> Path:
    queue = json.loads(queue_path.read_text())
    project_root = queue_path.parents[2]
    selected = select_calibration(rank_path, allow_density_reject)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []

    for value in queue["manifests"]:
        source = Path(value)
        if not source.is_absolute():
            source = project_root / source
        case = copy.deepcopy(json.loads(source.read_text()))
        case["case_id"] += "-cpt-informed"
        case["model_status"] = "cpt_informed_resolution_transfer_screen"
        case["purpose"] = (
            "Comparative wheel screen using the CPT-selected contact parameters. The 4 mm "
            "particle resolution is an acceleration layer; absolute compaction prediction "
            "remains withheld until a finalist passes a 2 mm and physical validation check."
        )
        terrain = case["terrain"]
        for key in MATERIAL_KEYS:
            terrain[key] = selected[key]
        terrain["calibration_status"] = (
            f"parameters selected from {selected['case_id']}; transferred to coarse wheel resolution"
        )
        case["cpt_calibration_provenance"] = {
            "ranking_file": str(rank_path.resolve()),
            "ranking_sha256": sha256_file(rank_path),
            "selected_case_id": selected["case_id"],
            "selection_score": selected["selection_score"],
            "density_gate_status": selected.get("density_gate_status"),
            "q100_ratio_predicted_to_observed": selected["q100_ratio"],
            "post_release_bulk_density_kg_m3": selected.get(
                "post_release_bulk_density_kg_m3"
            ),
            "resolution_transfer": {
                "cpt_particle_radius_m": selected["particle_radius_m"],
                "wheel_particle_radius_m": terrain["base_particle_radius_m"],
                "absolute_prediction_status": "WITHHELD_PENDING_CONVERGENCE_AND_PHYSICAL_VALIDATION",
            },
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)

    output_queue = output_dir / "wheel_screen_cpt_informed_queue.json"
    output_queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected_cpt_case_id": selected["case_id"],
                "manifests": [str(path.relative_to(project_root)) for path in manifests],
                "run_policy": (
                    "Run Alabama, smooth control, broad wave, and low grouser first. "
                    "Rank before committing to other candidates or 2 mm finalists."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return output_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("cases/wheel_screen/wheel_screen_master_queue.json"),
    )
    parser.add_argument("--rank", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("cases/wheel_screen_cpt"))
    parser.add_argument("--allow-density-reject", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = create_cases(
        args.queue.resolve(),
        args.rank.resolve(),
        args.output_dir.resolve(),
        args.allow_density_reject,
    )
    print(queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
