#!/usr/bin/env python3
"""Locate the earliest output-frame divergence across exact DEM repeats."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


FRAME_PATTERN = re.compile(r"_(\d+)\.(?:csv|vtk)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def output_files(case_root: Path) -> dict[str, Path]:
    files = {}
    for path in case_root.glob("wheel/**/*"):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".vtk"}:
            continue
        files[str(path.relative_to(case_root))] = path
    return files


def diagnose(profile_root: Path) -> dict:
    repeat_roots = sorted(path for path in profile_root.glob("r*") if path.is_dir())
    cases = []
    for repeat_root in repeat_roots:
        result_paths = list(repeat_root.glob("*/wheel_performance.json"))
        if len(result_paths) != 1:
            continue
        case_root = result_paths[0].parent
        cases.append(
            {
                "repeat": repeat_root.name,
                "case_root": case_root,
                "files": output_files(case_root),
            }
        )
    common = set.intersection(*(set(case["files"]) for case in cases)) if cases else set()
    comparisons = []
    for relative in sorted(common):
        hashes = [sha256_file(case["files"][relative]) for case in cases]
        match = FRAME_PATTERN.search(relative)
        comparisons.append(
            {
                "relative_path": relative,
                "frame": int(match.group(1)) if match else None,
                "sha256_by_repeat": dict(
                    zip((case["repeat"] for case in cases), hashes)
                ),
                "identical": len(set(hashes)) == 1,
            }
        )
    divergent_frames = [
        row["frame"]
        for row in comparisons
        if not row["identical"] and row["frame"] is not None
    ]
    first_frame = min(divergent_frames) if divergent_frames else None
    return {
        "schema_version": 1,
        "status": (
            "NO_COMPLETE_REPEAT_SET"
            if len(cases) < 2
            else "IDENTICAL_OUTPUTS"
            if all(row["identical"] for row in comparisons)
            else "DIVERGENT_OUTPUTS"
        ),
        "profile_root": str(profile_root),
        "repeats_compared": [case["repeat"] for case in cases],
        "common_output_files": len(comparisons),
        "first_divergent_frame": first_frame,
        "first_divergent_time_s": first_frame / 1000 if first_frame is not None else None,
        "comparisons": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    args = parser.parse_args()
    result = diagnose(args.profile_root.resolve())
    args.json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    print(f"first divergent frame: {result['first_divergent_frame']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
