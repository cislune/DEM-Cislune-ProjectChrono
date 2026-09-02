#!/usr/bin/env python3
"""Rank Alabama wheel-friction cases against the RIDER calibration split."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def collect(output_root: Path) -> list[dict]:
    rows = []
    for result_path in sorted(
        output_root.glob("calibrate-alabama-wheel-friction-*/wheel_performance.json")
    ):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        target = float(manifest["calibration_target"]["median_abs_torque_nm"])
        predicted = result["mobility"]["torque_y_nm"].get("median_abs")
        if predicted is None:
            continue
        density_gate = result.get("density_gate") or {}
        rows.append(
            {
                "case_id": result["case_id"],
                "wheel_friction": float(manifest["terrain"]["wheel_friction"]),
                "predicted_median_abs_torque_nm": float(predicted),
                "target_median_abs_torque_nm": target,
                "torque_ratio_predicted_to_observed": float(predicted) / target,
                "absolute_torque_error_nm": abs(float(predicted) - target),
                "relative_torque_error": abs(float(predicted) - target) / target,
                "density_gate_status": density_gate.get("status"),
                "achieved_to_target_density_ratio": density_gate.get(
                    "achieved_to_target_ratio"
                ),
                "result_status": result["status"],
                "result_json": str(result_path),
            }
        )
    return sorted(rows, key=lambda row: row["absolute_torque_error_nm"])


def write(rows: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    if rows:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = collect(args.output_root.resolve())
    write(rows, args.json_path.resolve(), args.csv_path.resolve())
    for index, row in enumerate(rows, 1):
        print(
            f"{index}. mu={row['wheel_friction']:.3g}: "
            f"torque={row['predicted_median_abs_torque_nm']:.3f} Nm, "
            f"error={row['relative_torque_error']:.1%}, "
            f"density={row['density_gate_status']}"
        )
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
