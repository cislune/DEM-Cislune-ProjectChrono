#!/usr/bin/env python3
"""Repeat the selected density-preparation margin across independent seeds."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_manifest(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def portable_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def generate(
    ranking_path: Path,
    queue_path: Path,
    output_dir: Path,
    seeds: list[int],
) -> Path:
    if not seeds or any(seed < 0 for seed in seeds):
        raise ValueError("Seeds must be a nonempty list of nonnegative integers")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be unique")

    ranking = json.loads(ranking_path.read_text())
    if not ranking:
        raise ValueError("Density ranking is empty")
    selected = ranking[0]
    queue = json.loads(queue_path.read_text())
    project_root = Path(__file__).resolve().parent
    selected_case = None
    selected_path = None
    for value in queue["manifests"]:
        path = resolve_manifest(project_root, value)
        case = json.loads(path.read_text())
        if case["case_id"] == selected["case_id"]:
            selected_case = case
            selected_path = path
            break
    if selected_case is None or selected_path is None:
        raise ValueError(f"Selected density case is absent from queue: {selected['case_id']}")

    original_seed = int(selected_case["terrain"].get("random_seed", 77))
    if original_seed in seeds:
        raise ValueError("Requested seeds must not repeat the margin-sweep seed")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    source_hash = sha256_file(selected_path)
    for seed in seeds:
        case = deepcopy(selected_case)
        case["case_id"] = f"{selected_case['case_id']}-seed{seed}"
        case["model_status"] = "deterministic_density_preparation_seed_repeat"
        case["purpose"] = (
            "Confirm the selected compression-release margin across independent terrain "
            "realizations before using the bed for finer wheel validation."
        )
        case["terrain"]["random_seed"] = seed
        case["density_seed_repeat"] = {
            "source_case_id": selected_case["case_id"],
            "source_manifest": portable_path(selected_path, project_root),
            "source_manifest_sha256": source_hash,
            "selected_compression_release_margin": float(
                selected_case["terrain"]["compression_release_margin"]
            ),
            "original_seed": original_seed,
            "repeat_seed": seed,
        }
        destination = output_dir / f"{case['case_id']}.json"
        destination.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifests.append(portable_path(destination, project_root))

    output_queue = output_dir / "density_seed_repeat_queue.json"
    output_queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected_case_id": selected_case["case_id"],
                "selected_margin": float(
                    selected_case["terrain"]["compression_release_margin"]
                ),
                "original_seed": original_seed,
                "repeat_seeds": seeds,
                "manifests": manifests,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return output_queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ranking", type=Path)
    parser.add_argument("queue", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", default="78,79")
    args = parser.parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    output = generate(
        args.ranking.resolve(),
        args.queue.resolve(),
        args.output_dir.resolve(),
        seeds,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
