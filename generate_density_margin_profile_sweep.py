#!/usr/bin/env python3
"""Generate density-preparation margins under one deterministic solver profile."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from generate_full_duration_solver_profile_case import SOLVER_PROFILE_KEYS
from generate_solver_determinism_probe_cases import PROFILES


def label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    project_root = Path(__file__).resolve().parent
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path.resolve())


def generate(
    source_path: Path,
    output_dir: Path,
    margins: list[float],
    profile: str = "cub-fixed-bin-cd1",
) -> Path:
    if profile not in PROFILES:
        raise ValueError(f"Unsupported solver profile: {profile}")
    if not margins or any(value < 0 for value in margins):
        raise ValueError("Density margins must be a nonempty list of nonnegative values")
    if len(set(margins)) != len(margins):
        raise ValueError("Density margins must be unique")

    source = json.loads(source_path.read_text())
    terrain = source["terrain"]
    target_density = float(terrain["target_bulk_density_kg_m3"])
    particle_density = float(terrain["particle_density_kg_m3"])
    if target_density * (1 + max(margins)) >= particle_density:
        raise ValueError("Requested compressed bulk density exceeds particle density")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    source_hash = sha256_file(source_path)
    radius_mm = float(terrain["base_particle_radius_m"]) * 1000
    for margin in margins:
        case = deepcopy(source)
        case["case_id"] = (
            f"density-r{label(radius_mm)}mm-margin{label(margin)}-{profile}"
        )
        case["model_status"] = "deterministic_density_preparation_margin_sweep"
        case["purpose"] = (
            "Measure post-release bed density while varying only compression-release "
            "margin under the patched deterministic solver profile."
        )
        case["allowed_stages"] = ["preflight", "terrain"]
        case["terrain"].pop("initial_state_csv", None)
        case["terrain"]["compression_release_margin"] = margin
        case["solver"] = deepcopy(case.get("solver", {}))
        for key in SOLVER_PROFILE_KEYS:
            case["solver"].pop(key, None)
        case["solver"].update(PROFILES[profile])
        case["density_margin_profile_sweep"] = {
            "source_manifest": portable_path(source_path),
            "source_manifest_sha256": source_hash,
            "base_particle_radius_m": float(terrain["base_particle_radius_m"]),
            "compression_release_margin": margin,
            "solver_profile": profile,
            "qualification": (
                "Terrain-preparation calibration only. Repeat the selected margin across "
                "independent seeds before using the bed for physical prediction."
            ),
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(portable_path(destination))

    queue_path = output_dir / "density_margin_profile_sweep_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": (
                    "Select a post-release density margin under the deterministic CD1 "
                    "solver before finer full-wheel validation."
                ),
                "source_manifest": portable_path(source_path),
                "source_manifest_sha256": source_hash,
                "solver_profile": profile,
                "manifests": manifests,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return queue_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--margins", default="0.18,0.35,0.55")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="cub-fixed-bin-cd1")
    args = parser.parse_args()
    margins = [float(value.strip()) for value in args.margins.split(",") if value.strip()]
    queue = generate(
        args.source_manifest.resolve(),
        args.output_dir.resolve(),
        margins,
        args.profile,
    )
    print(queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
