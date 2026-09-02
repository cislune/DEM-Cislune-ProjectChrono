#!/usr/bin/env python3
"""Score simulated RTGS wheel ordering against historical RIDER current ordering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def ordering_score(rows: list[dict], physical_key: str, simulated_key: str, *, physical_reverse: bool) -> dict:
    physical_order = [
        row["design"]
        for row in sorted(rows, key=lambda row: row[physical_key], reverse=physical_reverse)
    ]
    simulated_order = [
        row["design"]
        for row in sorted(rows, key=lambda row: row[simulated_key], reverse=True)
    ]
    pairs = 0
    concordant = 0
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            a, b = rows[left], rows[right]
            physical_sign = (
                a[physical_key] > b[physical_key]
                if physical_reverse
                else a[physical_key] < b[physical_key]
            )
            simulated_sign = a[simulated_key] > b[simulated_key]
            pairs += 1
            concordant += physical_sign == simulated_sign
    return {
        "physical_high_to_low_performance": physical_order,
        "simulated_high_to_low_performance": simulated_order,
        "concordant_pair_fraction": concordant / pairs if pairs else None,
        "exact_order_match": physical_order == simulated_order,
    }


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
                "physical_median_slip": float(target["measured_median_slip"]),
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
    complete = len(rows) == 3
    motor_demand = ordering_score(
        rows,
        "physical_current_reading",
        "simulated_median_abs_contact_torque_nm",
        physical_reverse=True,
    )
    mobility = ordering_score(
        rows,
        "physical_median_slip",
        "simulated_median_drawbar_to_normal",
        physical_reverse=False,
    )
    return {
        "schema_version": 1,
        "status": (
            "FAIL_MOTOR_DEMAND_ORDER_PARTIAL_MOBILITY_ORDER"
            if complete
            and motor_demand["concordant_pair_fraction"] == 0.0
            and mobility["concordant_pair_fraction"] > 0.0
            else "COMPLETE"
            if complete
            else "PARTIAL"
        ),
        "motor_demand_ordering": motor_demand,
        "mobility_ordering": mobility,
        "qualification": (
            "Historical currentReading units and tare are unknown; its ordinal result is "
            "reported but weak evidence. Physical slip has known dimensionless units and is "
            "compared with simulated drawbar efficiency as a separate mobility ordering. "
            "The shared 8 mm bed retains a density mismatch and does not support absolute claims."
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
    for name in ("motor_demand_ordering", "mobility_ordering"):
        ordering = result[name]
        print(name)
        print(
            f"physical:  {' > '.join(ordering['physical_high_to_low_performance'])}"
        )
        print(
            f"simulated: {' > '.join(ordering['simulated_high_to_low_performance'])}"
        )
        print(f"concordant pairs: {ordering['concordant_pair_fraction']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
