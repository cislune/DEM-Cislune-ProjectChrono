#!/usr/bin/env python3
"""Compute comparative compaction and mobility metrics from one wheel pass."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from analyze_dem_output import read_legacy_vtk_points
from dem_case_runner import source_file_provenance
from verify_reference_spin import verify as verify_reference_spin


ANALYSIS_SOURCE_FILES = (
    "analyze_dem_output.py",
    "analyze_wheel_performance.py",
    "verify_reference_spin.py",
)


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def read_particles(path: Path) -> list[tuple[float, float, float]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"X", "Y", "Z"}.issubset(reader.fieldnames):
            raise ValueError(f"Missing particle coordinates in {path}")
        return [(float(row["X"]), float(row["Y"]), float(row["Z"])) for row in reader]


def wheel_centers(paths: list[Path]) -> dict[int, tuple[float, float, float]]:
    result = {}
    for path in paths:
        frame = int(path.stem.rsplit("_", 1)[-1])
        center = read_legacy_vtk_points(path)["bounds_center"]
        result[frame] = (center["x_m"], center["y_m"], center["z_m"])
    return result


def contact_metrics(
    path: Path, center: tuple[float, float, float]
) -> dict[str, float | int]:
    sum_fx = 0.0
    sum_fy = 0.0
    sum_fz = 0.0
    torque_y = 0.0
    contacts = 0
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("contact_type") != "SM":
                continue
            fx, fy, fz = (float(row[key]) for key in ("f_x", "f_y", "f_z"))
            x, _, z = (float(row[key]) for key in ("X", "Y", "Z"))
            sum_fx += fx
            sum_fy += fy
            sum_fz += fz
            torque_y += (z - center[2]) * fx - (x - center[0]) * fz
            contacts += 1
    return {
        "contacts": contacts,
        "force_x_n": sum_fx,
        "force_y_n": sum_fy,
        "force_z_n": sum_fz,
        "torque_y_nm": torque_y,
    }


def describe(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "median_abs": statistics.median(abs(value) for value in values) if values else None,
        "p95_abs": quantile([abs(value) for value in values], 0.95) if values else None,
        "max_abs": max((abs(value) for value in values), default=None),
    }


def density_gate(case_dir: Path, tolerance_fraction: float = 0.03) -> dict | None:
    path = case_dir / "terrain" / "terrain_preparation.json"
    if not path.is_file():
        return None
    preparation = json.loads(path.read_text())
    target = preparation.get("target_bulk_density_kg_m3")
    achieved = preparation.get("post_release_bulk_density_kg_m3")
    if target is None or achieved is None:
        return None
    ratio = float(achieved) / float(target)
    passed = abs(ratio - 1.0) <= tolerance_fraction
    return {
        "status": "PASS_DENSITY" if passed else "REJECT_DENSITY_MISMATCH",
        "target_bulk_density_kg_m3": target,
        "achieved_bulk_density_kg_m3": achieved,
        "achieved_to_target_ratio": ratio,
        "tolerance_fraction": tolerance_fraction,
    }


def lane_metrics(
    initial: list[tuple[float, float, float]],
    final: list[tuple[float, float, float]],
    x_min: float,
    x_max: float,
    half_width: float,
    minimum_particles: int = 10,
) -> dict[str, float | int]:
    if len(initial) != len(final):
        raise ValueError("Initial and final particle counts differ")
    indices = [
        index
        for index, (x, y, _) in enumerate(initial)
        if x_min <= x <= x_max and abs(y) <= half_width
    ]
    if minimum_particles < 2:
        raise ValueError("minimum_particles must be at least 2")
    if len(indices) < minimum_particles:
        raise ValueError(
            "Too few particles in the wheel lane for compaction metrics: "
            f"found {len(indices)}, require {minimum_particles}"
        )
    initial_z = [initial[index][2] for index in indices]
    final_z = [final[index][2] for index in indices]
    initial_height = quantile(initial_z, 0.95) - quantile(initial_z, 0.05)
    final_height = quantile(final_z, 0.95) - quantile(final_z, 0.05)
    top_settlement = quantile(initial_z, 0.95) - quantile(final_z, 0.95)
    return {
        "particles": len(indices),
        "initial_p05_to_p95_height_m": initial_height,
        "final_p05_to_p95_height_m": final_height,
        "p95_surface_settlement_m": top_settlement,
        "column_strain_proxy": (initial_height - final_height) / initial_height,
        "median_particle_vertical_displacement_m": statistics.median(
            final[index][2] - initial[index][2] for index in indices
        ),
    }


def analyze(case_dir: Path) -> dict:
    manifest = json.loads((case_dir / "frozen_case.json").read_text())
    analysis_policy = manifest.get("analysis", {})
    case_id = manifest["case_id"]
    slip = float(manifest["test"]["slip_ratios"][0])
    slip_label = f"{slip:.6f}".rstrip("0").rstrip(".")
    input_path = (
        case_dir
        / "cumulative_inputs"
        / f"slip_{slip_label}"
        / "pass_01"
        / "settled terrain data"
        / "settled_terrain_data.csv"
    )
    pass_dirs = sorted((case_dir / "wheel" / f"slip_{slip_label}").glob("pass_*"))
    if not pass_dirs:
        raise ValueError("No wheel-pass output directories were found")
    run_roots = [path / "Trial 1" / f"Slip {slip_label}" for path in pass_dirs]
    final_path = (
        run_roots[-1]
        / "settled data"
        / f"slip_sinkage_settled_data_slip_{slip_label}.csv"
    )
    centers_by_pass = [
        wheel_centers(sorted((root / "wheel motion").glob("*.vtk"))) for root in run_roots
    ]
    if any(len(centers) < 2 for centers in centers_by_pass):
        raise ValueError("At least two wheel frames are required")
    frame_metrics = []
    for pass_number, (root, centers) in enumerate(zip(run_roots, centers_by_pass), 1):
        for path in sorted((root / "contact forces").glob("*.csv")):
            frame = int(path.stem.rsplit("_", 1)[-1])
            if frame in centers:
                frame_metrics.append(
                    {"pass": pass_number, "frame": frame, **contact_metrics(path, centers[frame])}
                )
    active = [item for item in frame_metrics if item["contacts"] > 0]
    mobility_by_pass = []
    for pass_number in range(1, len(run_roots) + 1):
        pass_active = [item for item in active if item["pass"] == pass_number]
        pass_torque = [float(item["torque_y_nm"]) for item in pass_active]
        pass_drawbar = [float(item["force_x_n"]) for item in pass_active]
        pass_vertical = [float(item["force_z_n"]) for item in pass_active]
        mobility_by_pass.append(
            {
                "pass": pass_number,
                "active_contact_frames": len(pass_active),
                "torque_y_nm": describe(pass_torque),
                "drawbar_force_x_n": describe(pass_drawbar),
                "vertical_contact_force_n": describe(pass_vertical),
                "median_abs_drawbar_over_normal_load": (
                    statistics.median(abs(value) for value in pass_drawbar)
                    / float(manifest["test"]["normal_load_n"])
                    if pass_drawbar
                    else None
                ),
            }
        )
    first_centers = centers_by_pass[0]
    first_center = first_centers[min(first_centers)]
    last_center = first_centers[max(first_centers)]
    travel_min = min(first_center[0], last_center[0])
    travel_max = max(first_center[0], last_center[0])
    half_width = float(manifest["wheel"]["width_m"]) / 2.0 + 2.0 * float(
        manifest["terrain"]["base_particle_radius_m"]
    )
    initial = read_particles(input_path)
    final = read_particles(final_path)
    lane = lane_metrics(
        initial,
        final,
        travel_min,
        travel_max,
        half_width,
        int(analysis_policy.get("minimum_lane_particles", 10)),
    )
    normal_load = float(manifest["test"]["normal_load_n"])
    torque_values = [float(item["torque_y_nm"]) for item in active]
    drawbar_values = [float(item["force_x_n"]) for item in active]
    vertical_values = [float(item["force_z_n"]) for item in active]
    reference_spin_gate = verify_reference_spin(
        sorted((run_roots[0] / "wheel motion").glob("*.vtk")), manifest
    )
    result = {
        "schema_version": 1,
        "case_id": case_id,
        "model_status": manifest.get("model_status"),
        "source_model_status": manifest.get("source_model_status"),
        "analysis_source_provenance": source_file_provenance(
            Path(__file__).resolve().parent, ANALYSIS_SOURCE_FILES
        ),
        "status": "PASS_COMPARATIVE_METRICS" if active else "REJECT_NO_WHEEL_CONTACT",
        "analysis_policy": analysis_policy,
        "warnings": [],
        "passes_analyzed": len(run_roots),
        "wheel_travel_m": last_center[0] - first_center[0],
        "wheel_vertical_change_m": last_center[2] - first_center[2],
        "wheel_minimum_center_z_m": min(center[2] for center in centers.values()),
        "lane": lane,
        "mobility": {
            "active_contact_frames": len(active),
            "torque_y_nm": describe(torque_values),
            "drawbar_force_x_n": describe(drawbar_values),
            "vertical_contact_force_n": describe(vertical_values),
            "median_abs_drawbar_over_normal_load": (
                statistics.median(abs(value) for value in drawbar_values) / normal_load
                if drawbar_values
                else None
            ),
        },
        "mobility_by_pass": mobility_by_pass,
        "reference_spin_gate": reference_spin_gate,
        "interpretation": (
            "These metrics compare identically configured shapes. The lane strain proxy includes "
            "particle rearrangement and lateral flow; absolute compaction requires CPT calibration "
            "and held-out RIDER or CRATR validation."
        ),
    }
    result["density_gate"] = density_gate(
        case_dir, float(manifest["terrain"].get("bulk_density_tolerance_fraction", 0.03))
    )
    if result["density_gate"] and result["density_gate"]["status"].startswith("REJECT"):
        if analysis_policy.get("density_gate_affects_status", True):
            result["status"] = "REJECT_DENSITY_MISMATCH"
        else:
            result["warnings"].append(
                "Density mismatch retained as a warning by the software-checkout policy; "
                "do not interpret absolute compaction."
            )
    if reference_spin_gate["status"].startswith("REJECT"):
        result["status"] = "REJECT_REFERENCE_SPIN"
    output = case_dir / "wheel_performance.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = analyze(args.case_dir.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(rendered)
    print(rendered, end="")
    return 0 if result["status"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
