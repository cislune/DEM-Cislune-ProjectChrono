#!/usr/bin/env python3
"""Generate ten-lap repeated-traffic sequences for all printable wheel candidates."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from generate_alabama_lap_sequence import final_state_relative_path


def candidate_name(case: dict) -> str:
    value = str(case["case_id"])
    prefix = "process-"
    suffix = "-r8mm-dt5us-phase1p2s"
    if value.startswith(prefix) and value.endswith(suffix):
        return value[len(prefix) : -len(suffix)]
    return value.replace("process-", "", 1)


def generate(base_queue_path: Path, candidate_queue_path: Path, output_dir: Path) -> Path:
    project_root = base_queue_path.parents[2]
    base_queue = json.loads(base_queue_path.read_text())
    candidate_queue = json.loads(candidate_queue_path.read_text())
    base_paths = [project_root / value for value in base_queue["manifests"]]
    candidate_paths = [project_root / value for value in candidate_queue["manifests"]]
    if len(base_paths) != 10:
        raise ValueError(f"Expected 10 Alabama manifests, found {len(base_paths)}")
    if not candidate_paths:
        raise ValueError("Candidate queue is empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_queues = []
    for candidate_path in candidate_paths:
        candidate_case = json.loads(candidate_path.read_text())
        name = candidate_name(candidate_case)
        destination_dir = output_dir / name
        destination_dir.mkdir(parents=True, exist_ok=True)
        manifests = []
        previous_case_id = None
        previous_slip = None
        for lap, base_path in enumerate(base_paths, 1):
            case = copy.deepcopy(json.loads(base_path.read_text()))
            case_id = f"candidate-sequence-{name}-lap{lap:02d}"
            case["case_id"] = case_id
            case["model_status"] = "frozen_candidate_repeated_traffic_screen"
            case["purpose"] = (
                "Compare printable wheel geometry over the measured ten-lap Alabama load, "
                "speed, and slip history with material parameters and bed realization frozen."
            )
            case["wheel"] = copy.deepcopy(candidate_case["wheel"])
            case["terrain"]["wheel_friction"] = 0.9
            if previous_case_id is not None:
                case["terrain"]["initial_state_case_id"] = previous_case_id
                case["terrain"].pop("initial_state_filename", None)
                case["terrain"]["initial_state_relative_path"] = final_state_relative_path(
                    float(previous_slip)
                )
            case["candidate_sequence"] = {
                "candidate": name,
                "lap": lap,
                "shared_condition": "UCF Alabama RIDER 2026-08-04 load/speed/slip history",
                "wheel_friction": 0.9,
                "physical_torque_target_applicability": (
                    "None. Measured RIDER torque belongs to the Alabama wheel and is not a "
                    "candidate-wheel validation target."
                ),
                "qualification": (
                    "The 8 mm bed fails the physical density gate. Use normalized repeated-traffic "
                    "compaction and mobility comparisons only."
                ),
            }
            destination = destination_dir / f"{case_id}.json"
            destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
            manifests.append(destination)
            previous_case_id = case_id
            previous_slip = float(case["test"]["slip_ratios"][0])

        queue_path = destination_dir / "sequence_queue.json"
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "candidate": name,
                    "manifests": [
                        str(path.relative_to(project_root)) for path in manifests
                    ],
                    "state_transfer": "each lap imports the preceding lap final soil state",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        candidate_queues.append(queue_path)

    master_path = output_dir / "candidate_sequence_campaign.json"
    master_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign": "Printable candidate repeated-traffic screen",
                "candidate_queues": [
                    str(path.relative_to(project_root)) for path in candidate_queues
                ],
                "comparison": "Normalize cumulative and mobility metrics to smooth_control.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return master_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-queue",
        type=Path,
        default=Path(
            "cases/alabama_rider_sequence_mu0p9_r8mm/alabama_rider_sequence_queue.json"
        ),
    )
    parser.add_argument(
        "--candidate-queue",
        type=Path,
        default=Path(
            "cases/wheel_phase_screen_r8mm_dt5us_1p2s/process_checkout_queue.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("cases/candidate_sequences_mu0p9_r8mm")
    )
    args = parser.parse_args()
    master = generate(
        args.base_queue.resolve(),
        args.candidate_queue.resolve(),
        args.output_dir.resolve(),
    )
    print(f"Candidate sequence campaign: {master}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
