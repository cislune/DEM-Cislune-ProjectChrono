#!/usr/bin/env python3
"""Generate a bounded CPT material sweep around the UCF out-track state."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


DESIGNS = (
    ("e8-mu30-rr01-c0", 1e8, 0.30, 0.01, 0.0),
    ("e8-mu50-rr05-c50", 1e8, 0.50, 0.05, 50.0),
    ("e8-mu70-rr10-c100", 1e8, 0.70, 0.10, 100.0),
    ("e3p8-mu30-rr05-c100", 3e8, 0.30, 0.05, 100.0),
    ("e3p8-mu50-rr10-c0", 3e8, 0.50, 0.10, 0.0),
    ("e3p8-mu70-rr01-c50", 3e8, 0.70, 0.01, 50.0),
    ("e9-mu30-rr10-c50", 1e9, 0.30, 0.10, 50.0),
    ("e9-mu50-rr01-c100", 1e9, 0.50, 0.01, 100.0),
    ("e9-mu70-rr05-c0", 1e9, 0.70, 0.05, 0.0),
)


def generate(template_path: Path, output_dir: Path) -> list[Path]:
    template = json.loads(template_path.read_text())
    project_root = template_path.parents[1]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for label, youngs_modulus, friction, rolling_resistance, cohesion in DESIGNS:
        case = copy.deepcopy(template)
        case["case_id"] = f"cpt-out-track-{label}-r2mm"
        case["model_status"] = "density_matched_material_sweep"
        case["purpose"] = (
            "Fit the UCF out-track CPT profile at measured bulk density using a bounded "
            "Young's-modulus, friction, rolling-resistance, and cohesion design."
        )
        terrain = case["terrain"]
        terrain["base_particle_radius_m"] = 0.002
        terrain["youngs_modulus_pa"] = youngs_modulus
        terrain["particle_friction"] = friction
        terrain["rolling_resistance"] = rolling_resistance
        terrain["cohesion"] = cohesion
        terrain["time_step_s"] = 2e-6
        terrain["name"] = f"ucf-out-track-density-matched-{label}"
        terrain["calibration_status"] = "sweep candidate"
        case["output"]["penetration_frame_time_s"] = 0.001
        case["output"]["penetration_write_every_n_frames"] = 5
        case["output"]["write_contact_files"] = False
        path = output_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(path)
    queue = {
        "schema_version": 1,
        "template": str(template_path.relative_to(project_root)),
        "target_state": "out_track",
        "selection_metric": "calibration.score_lower_is_better",
        "manifests": [str(path.relative_to(project_root)) for path in manifests],
        "run_policy": (
            "Run three stiffness brackets first (cases 1, 5, 9). Continue the remaining six "
            "only after force scale and numerical stability are confirmed."
        ),
    }
    (output_dir / "cpt_sweep_queue.json").write_text(
        json.dumps(queue, indent=2, sort_keys=True) + "\n"
    )
    return manifests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("cases/cpt_alabama_out_track_deme_bracket.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("cases/cpt_sweep"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in generate(args.template.resolve(), args.output_dir.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
