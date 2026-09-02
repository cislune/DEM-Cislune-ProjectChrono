#!/usr/bin/env python3
"""Verify exact-repeat output files were independently written, not hardlinked."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from diagnose_exact_repeat_divergence import output_files


def audit(profile_root: Path) -> dict:
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
                "files": output_files(case_root),
            }
        )
    common = set.intersection(*(set(case["files"]) for case in cases)) if cases else set()
    shared_storage = []
    files = []
    for relative in sorted(common):
        rows = []
        storage_ids = []
        for case in cases:
            stat = case["files"][relative].stat()
            storage_id = (stat.st_dev, stat.st_ino)
            storage_ids.append(storage_id)
            rows.append(
                {
                    "repeat": case["repeat"],
                    "device": stat.st_dev,
                    "inode": stat.st_ino,
                    "link_count": stat.st_nlink,
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        independent = len(storage_ids) == len(set(storage_ids))
        if not independent:
            shared_storage.append(relative)
        files.append(
            {
                "relative_path": relative,
                "independently_stored": independent,
                "by_repeat": rows,
            }
        )
    return {
        "schema_version": 1,
        "status": (
            "NO_COMPLETE_REPEAT_SET"
            if len(cases) < 2
            else "SHARED_OUTPUT_STORAGE_DETECTED"
            if shared_storage
            else "INDEPENDENT_OUTPUTS"
        ),
        "profile_root": str(profile_root),
        "repeats_audited": [case["repeat"] for case in cases],
        "common_output_files": len(files),
        "shared_storage_paths": shared_storage,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    args = parser.parse_args()
    result = audit(args.profile_root.resolve())
    args.json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    print(f"common output files: {result['common_output_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
