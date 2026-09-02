#!/usr/bin/env python3
"""Crop a wheel-lane terrain state and build a held-out post-traffic CPT case."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from analyze_wheel_performance import wheel_centers
from cpt_reference import sha256_file


def template_index(label: str) -> int:
    normalized = label.strip().lower()
    if normalized.startswith("t"):
        normalized = normalized[1:]
    return int(normalized)


def crop_state(
    source: Path,
    output: Path,
    x_center: float,
    y_center: float,
    bin_x: float,
    bin_y: float,
    particle_radius: float,
    z_shift: float,
) -> tuple[int, list[dict[str, str]]]:
    margin = 1.15 * particle_radius
    with source.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"X", "Y", "Z", "clump_type"}.issubset(reader.fieldnames):
            raise ValueError(f"Missing terrain columns in {source}")
        selected = []
        for row in reader:
            x = float(row["X"])
            y = float(row["Y"])
            if abs(x - x_center) <= bin_x / 2.0 - margin and abs(y - y_center) <= bin_y / 2.0 - margin:
                copied = dict(row)
                copied["X"] = f"{x - x_center:.12g}"
                copied["Y"] = f"{y - y_center:.12g}"
                copied["Z"] = f"{float(row['Z']) + z_shift:.12g}"
                selected.append(copied)
    if len(selected) < 50:
        raise ValueError(f"Only {len(selected)} particles fall inside the CPT crop")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(selected)
    return len(selected), selected


def build_case(wheel_case_dir: Path, template_path: Path, output_dir: Path) -> tuple[Path, Path]:
    wheel_manifest = json.loads((wheel_case_dir / "frozen_case.json").read_text())
    template = json.loads(template_path.read_text())
    slip = float(wheel_manifest["test"]["slip_ratios"][0])
    slip_label = f"{slip:.6f}".rstrip("0").rstrip(".")
    pass_dirs = sorted((wheel_case_dir / "wheel" / f"slip_{slip_label}").glob("pass_*"))
    if not pass_dirs:
        raise ValueError("No completed wheel passes were found")
    first_run = pass_dirs[0] / "Trial 1" / f"Slip {slip_label}"
    centers = wheel_centers(sorted((first_run / "wheel motion").glob("*.vtk")))
    x_center = 0.5 * (centers[min(centers)][0] + centers[max(centers)][0])
    y_center = 0.5 * (centers[min(centers)][1] + centers[max(centers)][1])
    final_run = pass_dirs[-1] / "Trial 1" / f"Slip {slip_label}"
    source = (
        final_run
        / "settled data"
        / f"slip_sinkage_settled_data_slip_{slip_label}.csv"
    )
    terrain = template["terrain"]
    wheel_terrain = wheel_manifest["terrain"]
    particle_radius = float(wheel_terrain["base_particle_radius_m"])
    cpt_floor = -float(terrain["bed_depth_m"]) / 2.0
    wheel_floor = -float(wheel_terrain["bed_depth_m"]) / 2.0
    state_path = output_dir / "post_wheel_track_sample.csv"
    count, rows = crop_state(
        source,
        state_path,
        x_center,
        y_center,
        float(terrain["bin_x_m"]),
        float(terrain["bin_y_m"]),
        particle_radius,
        cpt_floor - wheel_floor,
    )

    particle_density = float(wheel_terrain["particle_density_kg_m3"])
    total_mass = 0.0
    max_surface = cpt_floor
    for row in rows:
        radius = particle_radius * (1.0 + template_index(row["clump_type"]) / 100.0)
        total_mass += particle_density * (4.0 / 3.0) * math.pi * radius**3
        max_surface = max(max_surface, float(row["Z"]) + radius)
    apparent_density = total_mass / (
        float(terrain["bin_x_m"])
        * float(terrain["bin_y_m"])
        * (max_surface - cpt_floor)
    )

    case = template
    case["case_id"] = f"validate-{wheel_manifest['case_id']}-post-wheel-cpt"
    case["model_status"] = "held_out_post_wheel_virtual_cpt"
    case["purpose"] = (
        "Apply the out-track-calibrated cone model without refitting to a terrain sample cropped "
        "from the final simulated wheel lane and compare with the UCF in-track CPT profile."
    )
    case["terrain"].update(
        {
            "initial_state_csv": str(state_path.resolve()),
            "base_particle_radius_m": particle_radius,
            "particle_density_kg_m3": particle_density,
            "initial_fill_height_m": max_surface - cpt_floor,
            "calibration_status": "parameters held fixed; imported post-wheel state",
        }
    )
    for key in (
        "target_bulk_density_kg_m3",
        "target_settled_bed_height_m",
        "compression_frame_time_s",
        "compression_speed_m_s",
        "compression_release_speed_m_s",
        "compression_max_time_s",
        "compression_release_margin",
        "post_compression_relax_s",
    ):
        case["terrain"].pop(key, None)
    case["probe"]["target_depth_m"] = min(
        float(case["probe"]["target_depth_m"]),
        max(0.05, max_surface - cpt_floor - 0.01),
    )
    case["physical_reference"]["target_state"] = "in_track"
    case["derived_initial_state"] = {
        "source_wheel_case": str(wheel_case_dir),
        "source_wheel_manifest_sha256": sha256_file(wheel_case_dir / "frozen_case.json"),
        "source_final_terrain": str(source),
        "source_final_terrain_sha256": sha256_file(source),
        "source_pass": len(pass_dirs),
        "crop_center_m": [x_center, y_center],
        "particles": count,
        "apparent_bulk_density_kg_m3": apparent_density,
        "note": "Apparent density includes the wall-clearance margin in the denominator.",
    }
    manifest_path = output_dir / f"{case['case_id']}.json"
    manifest_path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
    return manifest_path, state_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_case_dir", type=Path)
    parser.add_argument("cpt_template", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest, state = build_case(
        args.wheel_case_dir.resolve(), args.cpt_template.resolve(), args.output_dir.resolve()
    )
    print(f"Post-wheel CPT manifest: {manifest}")
    print(f"Cropped terrain state: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
