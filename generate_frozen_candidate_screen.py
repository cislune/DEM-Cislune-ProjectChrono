#!/usr/bin/env python3
"""Generate a small candidate-wheel screen using frozen Alabama parameters."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from generate_alabama_friction_sweep import (
    DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
    DEFAULT_BED_CASE_ID,
    DEFAULT_BED_PREPARATION_SHA256,
    DEFAULT_BED_TARGET_DENSITY_KG_M3,
)


CANDIDATES = {
    "smooth_control": "process-smooth_control-r8mm-dt5us-phase1p2s.json",
    "broad_wave_12": "process-broad_wave_12-r8mm-dt5us-phase1p2s.json",
    "chevron_wave_14": "process-chevron_wave_14-r8mm-dt5us-phase1p2s.json",
}


def generate(
    source_dir: Path,
    output_dir: Path,
    wheel_friction: float,
    bed_case_id: str = DEFAULT_BED_CASE_ID,
    bed_state_sha256: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        cases_root = next(parent for parent in source_dir.parents if parent.name == "cases")
    except StopIteration:
        cases_root = source_dir.parent
    project_root = cases_root.parent
    manifests = []
    for candidate, filename in CANDIDATES.items():
        case = copy.deepcopy(json.loads((source_dir / filename).read_text()))
        case["case_id"] = f"screen-frozen-{candidate}-r8mm"
        case["model_status"] = "cpt_and_alabama_informed_candidate_screen_pilot"
        case["purpose"] = (
            "Compare candidate geometry at the CPT-selected soil parameters, Alabama-selected "
            "wheel friction, shared terrain realization, and representative Alabama calibration condition."
        )
        case["terrain"].update(
            {
                "initial_state_case_id": bed_case_id,
                "initial_state_filename": "settled_terrain_data.csv",
                "wheel_friction": wheel_friction,
            }
        )
        case["test"].update(
            {
                "normal_load_n": 9.05 * 9.80665,
                "linear_speed_m_s": 0.0980000000000074,
                "slip_ratios": [0.09119069549774234],
                "duration_s": 1.2,
                "passes": 1,
            }
        )
        case["analysis"] = {
            "minimum_lane_particles": 5,
            "density_gate_affects_status": False,
        }
        case["shared_sample_preparation"] = {
            "source_preparation_path": (
                f"case:{bed_case_id}/terrain/terrain_preparation.json"
            ),
            "source_preparation_sha256": DEFAULT_BED_PREPARATION_SHA256,
            "target_bulk_density_kg_m3": DEFAULT_BED_TARGET_DENSITY_KG_M3,
            "post_release_bulk_density_kg_m3": DEFAULT_BED_ACHIEVED_DENSITY_KG_M3,
            "achieved_to_target_ratio": (
                DEFAULT_BED_ACHIEVED_DENSITY_KG_M3
                / DEFAULT_BED_TARGET_DENSITY_KG_M3
            ),
            "random_seed": 77,
        }
        case["frozen_screen_provenance"] = {
            "candidate": candidate,
            "wheel_friction": wheel_friction,
            "wheel_friction_selected_from": "UCF Alabama RIDER laps 1-5",
            "soil_parameters_selected_from": "UCF Alabama out-track CPT",
            "shared_bed_case_id": bed_case_id,
            "shared_bed_state_sha256": bed_state_sha256,
            "qualification": (
                "The 8 mm bed fails the physical density gate. Use normalized candidate "
                "comparisons only; withhold absolute compaction prediction."
            ),
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(destination)
    queue = output_dir / "frozen_candidate_screen_queue.json"
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifests": [
                    str(path.relative_to(project_root)) for path in manifests
                ],
                "frozen_wheel_friction": wheel_friction,
                "comparison": "Shared-condition geometry screen; normalize to smooth control.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir", type=Path, default=Path("cases/wheel_phase_screen_r8mm_dt5us_1p2s")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/frozen_candidate_screen_r8mm")
    )
    parser.add_argument("--wheel-friction", type=float, required=True)
    parser.add_argument("--bed-case-id", default=DEFAULT_BED_CASE_ID)
    parser.add_argument("--bed-state-sha256")
    args = parser.parse_args()
    queue = generate(
        args.source_dir.resolve(),
        args.output_dir.resolve(),
        args.wheel_friction,
        args.bed_case_id,
        args.bed_state_sha256,
    )
    print(f"Frozen candidate screen: {queue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
