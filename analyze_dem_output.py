#!/usr/bin/env python3
"""Reject incomplete or numerically implausible PyDEME wheel-run outputs."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def describe(values: Iterable[float]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "n": len(finite),
        "min": min(finite) if finite else None,
        "median": statistics.median(finite) if finite else None,
        "p95": quantile(finite, 0.95),
        "max": max(finite) if finite else None,
    }


def read_xyz_csv(path: Path) -> dict[str, Any]:
    points: list[tuple[float, float, float]] = []
    nonfinite = 0
    nonfinite_orientation = 0
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"X", "Y", "Z"}.issubset(reader.fieldnames):
            raise ValueError(f"{path} does not contain X, Y, Z columns")
        for row in reader:
            point = tuple(float(row[axis]) for axis in ("X", "Y", "Z"))
            if not all(math.isfinite(value) for value in point):
                nonfinite += 1
            if {"Qw", "Qx", "Qy", "Qz"}.issubset(reader.fieldnames):
                orientation = [float(row[key]) for key in ("Qw", "Qx", "Qy", "Qz")]
                if not all(math.isfinite(value) for value in orientation):
                    nonfinite_orientation += 1
            points.append(point)
    finite_points = [point for point in points if all(math.isfinite(value) for value in point)]
    bounds = {
        axis: [min(point[index] for point in finite_points), max(point[index] for point in finite_points)]
        for index, axis in enumerate(("x_m", "y_m", "z_m"))
    } if finite_points else {}
    return {
        "path": str(path),
        "rows": len(points),
        "nonfinite_rows": nonfinite,
        "nonfinite_orientation_rows": nonfinite_orientation,
        "bounds": bounds,
        "points": points,
    }


def read_contact_csv(path: Path) -> dict[str, Any]:
    magnitudes: dict[str, list[float]] = defaultdict(list)
    vector_sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    nonfinite = 0
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"contact_type", "f_x", "f_y", "f_z"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} does not contain the required contact columns")
        for row in reader:
            contact_type = row["contact_type"]
            vector = [float(row[key]) for key in ("f_x", "f_y", "f_z")]
            if not all(math.isfinite(value) for value in vector):
                nonfinite += 1
                continue
            magnitudes[contact_type].append(math.sqrt(sum(value * value for value in vector)))
            for index, value in enumerate(vector):
                vector_sums[contact_type][index] += value
    return {
        "path": str(path),
        "nonfinite_rows": nonfinite,
        "by_type": {
            key: {"force_magnitude_n": describe(values), "force_vector_sum_n": vector_sums[key]}
            for key, values in sorted(magnitudes.items())
        },
    }


def read_legacy_vtk_points(path: Path) -> dict[str, Any]:
    points: list[tuple[float, float, float]] = []
    with path.open(errors="strict") as stream:
        iterator = iter(stream)
        expected = None
        for line in iterator:
            if line.startswith("POINTS "):
                expected = int(line.split()[1])
                break
        if expected is None:
            raise ValueError(f"{path} has no POINTS section")
        for line in iterator:
            values = line.split()
            if not values:
                continue
            if len(values) != 3:
                break
            points.append(tuple(float(value) for value in values))
            if len(points) == expected:
                break
    if len(points) != expected:
        raise ValueError(f"{path} declared {expected} points but contained {len(points)}")
    bounds = {
        axis: [min(point[index] for point in points), max(point[index] for point in points)]
        for index, axis in enumerate(("x_m", "y_m", "z_m"))
    }
    center = {axis: statistics.fmean(value) for axis, value in bounds.items()}
    return {"path": str(path), "points": len(points), "bounds": bounds, "bounds_center": center}


def displacement_summary(first: list[tuple[float, float, float]], last: list[tuple[float, float, float]]) -> dict[str, Any]:
    if len(first) != len(last):
        return {"comparable": False, "reason": "particle counts differ"}
    magnitudes = [
        math.sqrt(sum((after[i] - before[i]) ** 2 for i in range(3)))
        for before, after in zip(first, last)
    ]
    return {"comparable": True, "magnitude_m": describe(magnitudes)}


def find_sorted(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def analyze(run_dir: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    terrain_files = find_sorted(run_dir, "terrain motion/*.csv")
    contact_files = find_sorted(run_dir, "contact forces/*.csv")
    wheel_files = find_sorted(run_dir, "wheel motion/*.vtk")
    settled_files = find_sorted(run_dir, "settled data/*.csv")

    terrain = [read_xyz_csv(path) for path in terrain_files]
    contacts = [read_contact_csv(path) for path in contact_files]
    wheels = [read_legacy_vtk_points(path) for path in wheel_files]
    settled = [read_xyz_csv(path) for path in settled_files]

    for category in (terrain, contacts, settled):
        for item in category:
            if item["nonfinite_rows"]:
                failures.append(f"{item['path']} contains {item['nonfinite_rows']} non-finite rows")
            if item.get("nonfinite_orientation_rows"):
                failures.append(
                    f"{item['path']} contains {item['nonfinite_orientation_rows']} non-finite orientation rows"
                )
    if terrain and settled and terrain[-1]["rows"] != settled[-1]["rows"]:
        failures.append(
            f"stale or incoherent output: last terrain frame has {terrain[-1]['rows']} particles "
            f"but settled output has {settled[-1]['rows']}"
        )
    if terrain and any(item["rows"] != terrain[0]["rows"] for item in terrain[1:]):
        failures.append("terrain particle count changed between written frames")
    if not settled:
        failures.append("final settled terrain output is missing")
    if not terrain:
        warnings.append("no terrain motion frames were written; settled-state integrity can still be checked")

    if manifest and terrain:
        terrain_cfg = manifest["terrain"]
        half_x = float(terrain_cfg["bin_travel_length_m"]) / 2.0
        half_y = float(terrain_cfg["bin_width_m"]) / 2.0
        floor_z = -float(terrain_cfg["bed_depth_m"]) / 2.0
        radius = float(terrain_cfg["base_particle_radius_m"])
        final_state = settled[-1] if settled else terrain[-1]
        bounds = final_state["bounds"]
        if not bounds:
            failures.append("final terrain state has no finite particle positions")
            bounds = {"x_m": [0.0, 0.0], "y_m": [0.0, 0.0], "z_m": [0.0, 0.0]}
        if bounds["x_m"][0] < -half_x - radius or bounds["x_m"][1] > half_x + radius:
            failures.append("terrain escaped the declared travel-axis domain")
        if bounds["y_m"][0] < -half_y - radius or bounds["y_m"][1] > half_y + radius:
            failures.append("terrain escaped the declared cross-track domain")
        if bounds["z_m"][0] < floor_z - radius:
            failures.append("terrain penetrated below the declared bin floor")

        normal_load = float(manifest["test"]["normal_load_n"])
        mesh_contact_rows = 0
        for item in contacts:
            for contact_type, stats in item["by_type"].items():
                if contact_type == "SM":
                    mesh_contact_rows += int(stats["force_magnitude_n"]["n"])
                maximum = stats["force_magnitude_n"]["max"]
                if maximum is not None and maximum > 100.0 * normal_load:
                    failures.append(
                        f"{Path(item['path']).name} {contact_type} contact force {maximum:.6g} N "
                        f"exceeds 100 times the commanded normal load"
                    )
        if manifest.get("output", {}).get("write_contact_forces", False) and mesh_contact_rows == 0:
            failures.append("no sphere-mesh wheel contacts were recorded in the written frames")

    first_last_displacement = (
        displacement_summary(terrain[0]["points"], terrain[-1]["points"])
        if len(terrain) >= 2
        else None
    )
    wheel_motion = None
    if len(wheels) >= 2:
        wheel_motion = {
            axis: wheels[-1]["bounds_center"][axis] - wheels[0]["bounds_center"][axis]
            for axis in ("x_m", "y_m", "z_m")
        }
        if manifest:
            frame_time = float(manifest.get("output", {}).get("wheel_frame_time_s", 1e-3))
            first_frame = int(Path(wheels[0]["path"]).stem.rsplit("_", 1)[-1])
            last_frame = int(Path(wheels[-1]["path"]).stem.rsplit("_", 1)[-1])
            expected_travel = (
                float(manifest["test"]["linear_speed_m_s"])
                * (last_frame - first_frame)
                * frame_time
            )
            if abs(wheel_motion["x_m"] - expected_travel) > max(1e-5, 0.05 * expected_travel):
                failures.append(
                    f"wheel travel {wheel_motion['x_m']:.6g} m does not match commanded written-frame travel {expected_travel:.6g} m"
                )

    for collection in (terrain, settled):
        for item in collection:
            item.pop("points", None)

    return {
        "schema_version": 1,
        "status": "REJECT" if failures else "PASS_SOFTWARE_INTEGRITY",
        "run_dir": str(run_dir.resolve()),
        "failures": failures,
        "warnings": warnings,
        "terrain_frames": terrain,
        "settled_outputs": settled,
        "contact_frames": contacts,
        "wheel_frames": wheels,
        "terrain_first_to_last_displacement": first_last_displacement,
        "wheel_bounds_center_first_to_last_m": wheel_motion,
        "interpretation": (
            "PASS_SOFTWARE_INTEGRITY only establishes internally coherent output. Absolute compaction "
            "prediction requires material calibration and held-out RIDER or CRATR validation."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text()) if args.manifest else None
    result = analyze(args.run_dir.resolve(), manifest)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered)
    print(rendered, end="")
    return 0 if result["status"] != "REJECT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
