#!/usr/bin/env python3
"""Generate short exact-manifest probes for DEM solver determinism."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


PROFILES = {
    "cub": {
        "sort_contact_pairs": True,
        "use_cub_force_collection": True,
    },
    "cub-fixed-bin": {
        "disable_adaptive_bin_size": True,
        "sort_contact_pairs": True,
        "use_cub_force_collection": True,
    },
    "cub-fixed-bin-cd20": {
        "cd_update_frequency": 20,
        "disable_adaptive_bin_size": True,
        "disable_adaptive_update_frequency": True,
        "sort_contact_pairs": True,
        "use_cub_force_collection": True,
    },
    "cub-fixed-bin-cd1": {
        "cd_update_frequency": 1,
        "disable_adaptive_bin_size": True,
        "disable_adaptive_update_frequency": True,
        "sort_contact_pairs": True,
        "use_cub_force_collection": True,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    project_root = Path(__file__).resolve().parent
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path.resolve())


def generate(
    source_manifest: Path,
    output_dir: Path,
    duration_s: float = 0.35,
    write_every: int = 25,
) -> dict:
    source = json.loads(source_manifest.read_text())
    source_hash = sha256_file(source_manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for profile, solver_overrides in PROFILES.items():
        case = copy.deepcopy(source)
        case["case_id"] = f"determinism-probe-alabama-{profile}"
        case["model_status"] = "short_exact_manifest_solver_determinism_probe"
        case["purpose"] = (
            "Measure numerical divergence while holding the manifest, case ID, wheel, "
            "and imported Alabama lap-2 terrain state byte-identical across repeats."
        )
        case.pop("repeatability_target", None)
        case["determinism_probe"] = {
            "duration_s": duration_s,
            "execution_profile": profile,
            "qualification": (
                "Short execution diagnostic only. It cannot calibrate physical response or "
                "replace the full-duration RIDER comparison."
            ),
            "repeats_requested": 3,
            "source_manifest": portable_path(source_manifest),
            "source_manifest_sha256": source_hash,
        }
        case["solver"] = copy.deepcopy(case.get("solver", {}))
        for key in (
            "cd_update_frequency",
            "disable_adaptive_bin_size",
            "disable_adaptive_update_frequency",
            "sort_contact_pairs",
            "use_cub_force_collection",
        ):
            case["solver"].pop(key, None)
        case["solver"].update(solver_overrides)
        case["test"]["duration_s"] = duration_s
        case["output"]["wheel_progress_every_n_frames"] = write_every
        case["output"]["wheel_write_every_n_frames"] = write_every
        path = output_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(portable_path(path))

    queue = {
        "schema_version": 1,
        "purpose": "Short exact-manifest solver determinism isolation before wheel ranking.",
        "source_manifest": portable_path(source_manifest),
        "source_manifest_sha256": source_hash,
        "duration_s": duration_s,
        "repeats_per_profile": 3,
        "manifests": manifests,
    }
    queue_path = output_dir / "determinism_probe_queue.json"
    queue_path.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n")
    return queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.35)
    parser.add_argument("--write-every", type=int, default=25)
    args = parser.parse_args()
    if args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args.write_every < 1:
        parser.error("--write-every must be positive")
    queue = generate(
        args.source_manifest.resolve(),
        args.output_dir.resolve(),
        args.duration_s,
        args.write_every,
    )
    print(json.dumps(queue, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
