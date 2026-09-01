#!/usr/bin/env python3
"""Rank terrain preparation cases by post-release bulk-density error."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def collect(output_root: Path) -> list[dict]:
    rows = []
    for preparation_path in sorted(output_root.glob("*/terrain/terrain_preparation.json")):
        case_dir = preparation_path.parent.parent
        frozen_path = case_dir / "frozen_case.json"
        if not frozen_path.is_file():
            continue
        preparation = json.loads(preparation_path.read_text())
        case = json.loads(frozen_path.read_text())
        target = float(preparation["target_bulk_density_kg_m3"])
        achieved = float(preparation["post_release_bulk_density_kg_m3"])
        margin = float(case["terrain"]["compression_release_margin"])
        rows.append(
            {
                "case_id": case["case_id"],
                "compression_release_margin": margin,
                "target_bulk_density_kg_m3": target,
                "post_release_bulk_density_kg_m3": achieved,
                "achieved_to_target_ratio": achieved / target,
                "absolute_density_error_kg_m3": abs(achieved - target),
                "particle_count": int(preparation["generated_particle_count"]),
            }
        )
    return sorted(rows, key=lambda row: row["absolute_density_error_kg_m3"])


def write_outputs(rows: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = collect(args.output_root.resolve())
    if not rows:
        raise SystemExit("No completed terrain preparation records found")
    json_path = args.json or args.output_root / "density-margin-ranking.json"
    csv_path = args.csv or args.output_root / "density-margin-ranking.csv"
    write_outputs(rows, json_path, csv_path)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
