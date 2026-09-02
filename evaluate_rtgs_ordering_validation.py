#!/usr/bin/env python3
"""Score simulated RTGS wheel ordering against historical RIDER current ordering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(output_root: Path) -> dict:
    rows = []
    for result_path in sorted(
        output_root.glob("validate-rtgs-*-r8mm-frozen/wheel_performance.json")
    ):
        result = json.loads(result_path.read_text())
        manifest = json.loads((result_path.parent / "frozen_case.json").read_text())
        target = manifest["ordinal_validation_target"]
        rows.append(
            {
                "design": target["design"],
                "physical_current_reading": float(
                    target["median_of_lap_median_abs_current_reading"]
                ),
                "simulated_median_abs_contact_torque_nm": float(
                    result["mobility"]["torque_y_nm"]["median_abs"]
                ),
                "simulated_median_drawbar_to_normal": float(
                    result["mobility"]["median_abs_drawbar_over_normal_load"]
                ),
                "density_gate_status": result["density_gate"]["status"],
                "result_json": str(result_path),
            }
        )
    if not rows:
        raise ValueError(f"No completed RTGS validation cases found in {output_root}")
    physical_order = [
        row["design"]
        for row in sorted(rows, key=lambda row: row["physical_current_reading"], reverse=True)
    ]
    simulated_order = [
        row["design"]
        for row in sorted(
            rows,
            key=lambda row: row["simulated_median_abs_contact_torque_nm"],
            reverse=True,
        )
    ]
    pairs = 0
    concordant = 0
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            a, b = rows[left], rows[right]
            physical_sign = a["physical_current_reading"] > b["physical_current_reading"]
            simulated_sign = (
                a["simulated_median_abs_contact_torque_nm"]
                > b["simulated_median_abs_contact_torque_nm"]
            )
            pairs += 1
            concordant += physical_sign == simulated_sign
    complete = len(rows) == 3
    return {
        "schema_version": 1,
        "status": "COMPLETE" if complete else "PARTIAL",
        "physical_high_to_low": physical_order,
        "simulated_high_to_low": simulated_order,
        "concordant_pair_fraction": concordant / pairs if pairs else None,
        "exact_order_match": complete and physical_order == simulated_order,
        "qualification": (
            "Historical currentReading units are unknown, so this is an ordinal geometry "
            "validation only. The shared 8 mm bed retains a density mismatch and does not "
            "support absolute compaction claims."
        ),
        "designs": sorted(rows, key=lambda row: row["design"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    args = parser.parse_args()
    result = evaluate(args.output_root.resolve())
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"physical:  {' > '.join(result['physical_high_to_low'])}")
    print(f"simulated: {' > '.join(result['simulated_high_to_low'])}")
    print(f"concordant pairs: {result['concordant_pair_fraction']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
