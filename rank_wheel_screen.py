#!/usr/bin/env python3
"""Rank comparable wheel cases on compaction with a mobility guardrail."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


def canonical_wheel_name(case_id: str) -> str:
    name = case_id.removeprefix("screen-")
    name = name.removeprefix("process-")
    name = re.sub(r"-seed-?\d+$", "", name)
    for suffix in ("-shared-bed", "-cpt-informed", "-coarse"):
        name = name.removesuffix(suffix)
    name = re.sub(r"-r[^-]+mm-dt[^-]+us(?:-[A-Za-z0-9_.]+)?$", "", name)
    return name


def load_rows(output_root: Path) -> list[dict]:
    rows = []
    paths = sorted(output_root.glob("screen-*/wheel_performance.json"))
    paths.extend(sorted(output_root.glob("process-*/wheel_performance.json")))
    for path in paths:
        result = json.loads(path.read_text())
        if not result["status"].startswith("PASS"):
            continue
        manifest = json.loads((path.parent / "frozen_case.json").read_text())
        torque_summary = result["mobility"]["torque_y_nm"]
        torque = torque_summary.get("median_abs")
        if torque is None and torque_summary.get("median") is not None:
            torque = abs(torque_summary["median"])
        settlement = result["lane"]["p95_surface_settlement_m"]
        strain = result["lane"]["column_strain_proxy"]
        rows.append(
            {
                "case_id": result["case_id"],
                "wheel": canonical_wheel_name(result["case_id"]),
                "surface_settlement_mm": settlement * 1000.0,
                "column_strain_proxy_percent": strain * 100.0,
                "median_abs_torque_nm": torque,
                "median_abs_drawbar_over_normal_load": result["mobility"]["median_abs_drawbar_over_normal_load"],
                "feature_height_particle_radii": manifest["wheel"].get("feature_height_in_particle_radii"),
                "model_status": result["model_status"],
                "reference_spin_status": result.get("reference_spin_gate", {}).get("status"),
                "result_json": str(path),
            }
        )
    if not rows:
        return []
    smooth = next((row for row in rows if row["wheel"] == "smooth_control"), None)
    if smooth:
        torque_reference = max(smooth["median_abs_torque_nm"] or 0.0, 1e-9)
        drawbar_reference = max(
            smooth["median_abs_drawbar_over_normal_load"] or 0.0, 1e-9
        )
        settlement_reference = max(abs(smooth["surface_settlement_mm"]), 1e-9)
        strain_reference = max(abs(smooth["column_strain_proxy_percent"]), 1e-9)
        settlement_scale = max(
            max(abs(row["surface_settlement_mm"]) for row in rows), 0.1
        )
        strain_scale = max(
            max(abs(row["column_strain_proxy_percent"]) for row in rows), 0.01
        )
        for row in rows:
            torque_ratio = (row["median_abs_torque_nm"] or 0.0) / torque_reference
            row["torque_ratio_to_smooth"] = torque_ratio
            row["drawbar_ratio_to_smooth"] = (
                row["median_abs_drawbar_over_normal_load"] / drawbar_reference
            )
            row["settlement_ratio_to_smooth"] = (
                row["surface_settlement_mm"] / settlement_reference
            )
            row["strain_ratio_to_smooth"] = (
                row["column_strain_proxy_percent"] / strain_reference
            )
            spin_pass = row["reference_spin_status"] == "PASS_REFERENCE_SPIN"
            row["mobility_guardrail_pass"] = torque_ratio <= 1.35 and spin_pass
            signed_compaction_index = (
                0.6 * row["surface_settlement_mm"] / settlement_scale
                + 0.4 * row["column_strain_proxy_percent"] / strain_scale
            )
            row["signed_compaction_index_higher_is_better"] = signed_compaction_index
            row["screen_score_lower_is_better"] = (
                -signed_compaction_index
                + 0.35 * max(0.0, torque_ratio - 1.0)
            )
    return sorted(
        rows,
        key=lambda row: (
            not row.get("mobility_guardrail_pass", True),
            row.get("screen_score_lower_is_better", math.inf),
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_rows(args.output_root.resolve())
    args.csv_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields = sorted({key for row in rows for key in row})
        with args.csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    args.json_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    for index, row in enumerate(rows, 1):
        print(
            f"{index}. {row['wheel']}: settlement={row['surface_settlement_mm']:.3f} mm, "
            f"torque={row['median_abs_torque_nm']:.3f} Nm, guardrail={row.get('mobility_guardrail_pass')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
