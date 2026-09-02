#!/usr/bin/env python3
"""Preflight, run, and score a cone-penetrometer DEM calibration case."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import runpy
import shutil
import statistics
import sys
from types import SimpleNamespace
from typing import Any

from cpt_reference import interpolate, linear_fit, sha256_file
from dem_case_runner import git_revision, inspect_obj, require_deme, runtime_environment


class CptCaseError(ValueError):
    pass


def load_case(path: Path) -> dict[str, Any]:
    try:
        case = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CptCaseError(f"Cannot read case manifest {path}: {exc}") from exc
    for key in ("case_id", "probe", "terrain"):
        if key not in case:
            raise CptCaseError(f"Missing required field: {key}")
    if case.get("schema_version") != 1:
        raise CptCaseError("Only schema_version 1 is supported")
    return case


def resolve_path(project_root: Path, manifest_path: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    candidates = [raw] if raw.is_absolute() else [project_root / raw, manifest_path.parent / raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise CptCaseError(f"File not found: {value}")


def generate_probe_obj(path: Path, probe: dict[str, Any], slices: int = 48) -> None:
    base_radius = float(probe["base_diameter_m"]) / 2.0
    shaft_radius = float(probe["shaft_diameter_m"]) / 2.0
    half_angle = math.radians(float(probe["included_angle_deg"]) / 2.0)
    cone_height = base_radius / math.tan(half_angle)
    shaft_length = float(probe["shaft_length_m"])
    vertices = [(0.0, 0.0, 0.0)]
    for z, radius in (
        (cone_height, base_radius),
        (cone_height, shaft_radius),
        (cone_height + shaft_length, shaft_radius),
    ):
        for index in range(slices):
            theta = 2.0 * math.pi * index / slices
            vertices.append((radius * math.cos(theta), radius * math.sin(theta), z))
    vertices.append((0.0, 0.0, cone_height + shaft_length))

    outer_start = 1
    shaft_bottom_start = outer_start + slices
    shaft_top_start = shaft_bottom_start + slices
    top_center = len(vertices) - 1
    faces = []
    for index in range(slices):
        following = (index + 1) % slices
        outer = outer_start + index
        outer_next = outer_start + following
        shaft_bottom = shaft_bottom_start + index
        shaft_bottom_next = shaft_bottom_start + following
        shaft_top = shaft_top_start + index
        shaft_top_next = shaft_top_start + following
        faces.append((0, outer_next, outer))
        faces.extend(
            [
                (outer, outer_next, shaft_bottom_next),
                (outer, shaft_bottom_next, shaft_bottom),
                (shaft_bottom, shaft_bottom_next, shaft_top_next),
                (shaft_bottom, shaft_top_next, shaft_top),
                (top_center, shaft_top, shaft_top_next),
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write("# UCF GRASP CPT cone; +Z points from tip toward shaft\n")
        for x, y, z in vertices:
            stream.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
        for face in faces:
            stream.write("f " + " ".join(str(index + 1) for index in face) + "\n")


def estimated_particles(terrain: dict[str, Any]) -> int:
    radius = float(terrain["base_particle_radius_m"])
    fill_fraction = float(terrain.get("initial_solid_fraction", 0.55))
    fill_height = float(terrain.get("initial_fill_height_m", terrain["bed_depth_m"]))
    volume = float(terrain["bin_x_m"]) * float(terrain["bin_y_m"]) * fill_height
    return round(fill_fraction * volume / ((4.0 / 3.0) * math.pi * radius**3))


def csv_data_rows(path: Path) -> int:
    with path.open(newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def preflight_case(case_path: Path, project_root: Path, output_root: Path):
    case = load_case(case_path)
    case_dir = output_root / case["case_id"]
    probe_obj = case_dir / "input" / "ucf_cpt_probe.obj"
    generate_probe_obj(probe_obj, case["probe"])
    mesh = inspect_obj(probe_obj)
    failures = []
    warnings = []
    probe = case["probe"]
    terrain = case["terrain"]
    base_radius = float(probe["base_diameter_m"]) / 2.0
    particle_radius = float(terrain["base_particle_radius_m"])
    if not mesh["watertight_two_manifold"] or mesh["non_triangular_faces"]:
        failures.append("generated probe mesh failed watertight triangular-mesh QA")
    if float(probe["included_angle_deg"]) <= 0 or float(probe["included_angle_deg"]) >= 90:
        failures.append("included_angle_deg must be between 0 and 90 degrees")
    if float(probe["target_depth_m"]) >= float(terrain["bed_depth_m"]):
        failures.append("target depth must be less than bed depth")
    if float(probe["insertion_speed_m_s"]) <= 0:
        failures.append("insertion speed must be positive")
    if base_radius / particle_radius < 3.0:
        warnings.append(
            f"cone radius is only {base_radius / particle_radius:.2f} particle radii; "
            "this is a numerical checkout, not a resolution-converged prediction"
        )
    if case.get("model_status") != "calibrated_validation":
        warnings.append(
            f"model_status is {case.get('model_status', 'unspecified')}; absolute CPT predictions are not validated"
        )
    speed_status = probe.get("insertion_speed_status", "unspecified")
    if speed_status != "measured":
        warnings.append(
            f"insertion speed is {speed_status}; check rate sensitivity before physical interpretation"
        )

    reference_path = None
    reference = case.get("physical_reference", {})
    if reference.get("reference_json"):
        try:
            reference_path = resolve_path(project_root, case_path, reference["reference_json"])
        except CptCaseError as exc:
            failures.append(str(exc))

    initial_state_path = None
    if terrain.get("initial_state_csv"):
        try:
            initial_state_path = resolve_path(project_root, case_path, terrain["initial_state_csv"])
            case["_resolved_initial_state_csv"] = str(initial_state_path)
        except CptCaseError as exc:
            failures.append(str(exc))

    report = {
        "status": "FAIL" if failures else "PASS",
        "case_id": case["case_id"],
        "model_status": case.get("model_status"),
        "probe_mesh": mesh,
        "estimated_initial_particle_count": (
            csv_data_rows(initial_state_path) if initial_state_path else estimated_particles(terrain)
        ),
        "cone_radius_to_particle_radius": base_radius / particle_radius,
        "physical_reference_path": str(reference_path) if reference_path else None,
        "physical_reference_sha256": sha256_file(reference_path) if reference_path else None,
        "initial_state_path": str(initial_state_path) if initial_state_path else None,
        "initial_state_sha256": sha256_file(initial_state_path) if initial_state_path else None,
        "project_git_revision": git_revision(project_root),
        "warnings": warnings,
        "failures": failures,
    }
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "preflight.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    frozen = dict(case)
    frozen["provenance"] = {
        "manifest_path": str(case_path),
        "manifest_sha256": sha256_file(case_path),
        "probe_obj_sha256": mesh["sha256"],
        "physical_reference_path": str(reference_path) if reference_path else None,
        "physical_reference_sha256": report["physical_reference_sha256"],
        "initial_state_path": report["initial_state_path"],
        "initial_state_sha256": report["initial_state_sha256"],
        "project_git_revision": report["project_git_revision"],
    }
    (case_dir / "frozen_case.json").write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    paths = {
        "case_dir": case_dir,
        "probe_obj": probe_obj,
        "terrain": case_dir / "terrain",
        "penetration": case_dir / "penetration",
    }
    return case, paths, report


def apply_config(config: Any, case: dict[str, Any], paths: dict[str, Path]) -> None:
    probe = case["probe"]
    terrain = case["terrain"]
    solver = case.get("solver", {})
    output = case.get("output", {})
    gravity = float(case.get("gravity_m_s2", 9.81))
    config.USE_DEMO_WHEEL_st = False
    config.G_MAG_st = gravity
    config.GRAVITATIONAL_ACCELERATION_st = [0.0, 0.0, -gravity]
    config.BASE_TERRAIN_RAD_st = float(terrain["base_particle_radius_m"])
    config.TERRAIN_DENSITY_st = float(terrain["particle_density_kg_m3"])
    config.E_st = float(terrain["youngs_modulus_pa"])
    config.NU_st = float(terrain["poissons_ratio"])
    config.COR_st = float(terrain["coefficient_of_restitution"])
    config.MU_st = float(terrain["particle_friction"])
    config.CRR_st = float(terrain["rolling_resistance"])
    config.COHESION_st = float(terrain["cohesion"])
    config.STEP_SIZE_st = float(terrain["time_step_s"])
    config.WIDTH_st = float(terrain["bin_x_m"])
    config.LENGTH_st = float(terrain["bin_y_m"])
    config.DEPTH_st = float(terrain["bed_depth_m"])
    config.FULL_HEIGHT_st = -config.DEPTH_st / 2.0 + float(terrain["initial_fill_height_m"])
    config.TERRAIN_RANDOM_SEED_st = int(terrain.get("random_seed", 77))
    config.TERRAIN_SETTLE_TIME_S_st = float(terrain.get("settle_time_s", 0.5))
    target_density = terrain.get("target_bulk_density_kg_m3")
    target_height = terrain.get("target_settled_bed_height_m")
    if target_density is not None and target_height is not None:
        config.TERRAIN_TARGET_BULK_DENSITY_KG_M3_st = float(target_density)
        config.TERRAIN_TARGET_PARTICLE_MASS_KG_st = (
            float(target_density)
            * config.WIDTH_st
            * config.LENGTH_st
            * float(target_height)
        )
        config.TERRAIN_COMPRESSION_FRAME_TIME_S_st = float(
            terrain.get("compression_frame_time_s", 0.002)
        )
        config.TERRAIN_COMPRESSION_SPEED_M_S_st = float(
            terrain.get("compression_speed_m_s", 0.02)
        )
        config.TERRAIN_COMPRESSION_RELEASE_SPEED_M_S_st = float(
            terrain.get(
                "compression_release_speed_m_s",
                max(0.05, config.TERRAIN_COMPRESSION_SPEED_M_S_st),
            )
        )
        config.TERRAIN_COMPRESSION_MAX_TIME_S_st = float(
            terrain.get("compression_max_time_s", 10.0)
        )
        config.TERRAIN_COMPRESSION_RELEASE_MARGIN_st = float(
            terrain.get("compression_release_margin", 0.02)
        )
        config.TERRAIN_POST_COMPRESSION_RELAX_S_st = float(
            terrain.get("post_compression_relax_s", 0.2)
        )
    config.TERRAIN_FRAME_TIME_S_st = float(output.get("terrain_frame_time_s", 0.002))
    config.TERRAIN_WRITE_EVERY_N_FRAMES_st = int(output.get("terrain_write_every_n_frames", 100))
    config.TERRAIN_WRITE_MOTION_st = bool(output.get("write_terrain_settling_motion", False))
    config.TERRAIN_INITIAL_STATE_CSV_st = case.get("_resolved_initial_state_csv")
    config.TERRAIN_IMPORTED_PREPARATION_st = case.get("shared_sample_preparation")
    config.MAX_VELOCITY_st = float(solver.get("max_velocity_m_s", 10.0))
    config.ERROR_OUT_VELOCITY_st = float(solver.get("error_out_velocity_m_s", 20.0))
    config.MAX_TRIANGLES_IN_BIN_st = int(solver.get("max_triangles_in_bin", 10000))
    config.ERROR_OUT_AVG_CONTACTS_st = float(solver.get("error_out_avg_contacts", 100.0))
    config.SPHERE_TERRAIN_GEN_OUT_DIR = str(paths["terrain"])
    config.PENETROMETER_OUT_DIR = str(paths["penetration"])
    config.PENETROMETER_OBJ_FILE_st = str(paths["probe_obj"])
    config.PENETROMETER_MASS_st = float(probe.get("mass_kg", 1.0))
    config.PENETROMETER_SPEED_st = float(probe["insertion_speed_m_s"])
    config.PENETROMETER_TARGET_DEPTH_st = float(probe["target_depth_m"])
    config.PENETROMETER_CLEARANCE_st = float(probe.get("initial_clearance_m", 0.002))
    config.PENETROMETER_SHAFT_LENGTH_st = float(probe["shaft_length_m"])
    config.MU_contact_probe_st = float(probe.get("interface_friction", 0.3))
    config.COR_contact_probe_st = float(probe.get("interface_restitution", 0.1))
    config.COHESION_contact_probe_st = float(probe.get("interface_cohesion", 0.0))
    config.PENETROMETER_FRAME_TIME_S_st = float(output.get("penetration_frame_time_s", 0.001))
    config.PENETROMETER_PRE_RELAX_S_st = float(terrain.get("pre_penetration_relax_s", 0.0))
    config.PENETROMETER_WRITE_EVERY_N_FRAMES_st = int(output.get("penetration_write_every_n_frames", 1))
    config.PENETROMETER_WRITE_MESH_st = bool(output.get("write_probe_mesh_motion", False))
    config.PENETROMETER_WRITE_CONTACT_st = bool(output.get("write_contact_files", False))


def settled_terrain_path(root: Path) -> Path:
    return root / "settled terrain data" / "settled_terrain_data.csv"


def run_terrain(project_root: Path, config: Any, paths: dict[str, Path], overwrite: bool) -> None:
    target = settled_terrain_path(paths["terrain"])
    if target.exists() and not overwrite:
        print(f"Reusing settled terrain: {target}")
        return
    if paths["terrain"].exists() and overwrite:
        shutil.rmtree(paths["terrain"])
    initial_state = getattr(config, "TERRAIN_INITIAL_STATE_CSV_st", None)
    if initial_state:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(initial_state, target)
        preparation = {
            "preparation_mode": "imported_initial_state",
            "initial_state_path": str(initial_state),
            "initial_state_sha256": sha256_file(Path(initial_state)),
            "generated_particle_count": csv_data_rows(Path(initial_state)),
        }
        imported_preparation = getattr(config, "TERRAIN_IMPORTED_PREPARATION_st", None)
        if imported_preparation:
            preparation.update(
                {
                    "source_preparation_path": imported_preparation.get(
                        "source_preparation"
                    ),
                    "source_preparation_sha256": imported_preparation.get(
                        "source_preparation_sha256"
                    ),
                    "target_bulk_density_kg_m3": imported_preparation.get(
                        "target_bulk_density_kg_m3"
                    ),
                    "post_release_bulk_density_kg_m3": imported_preparation.get(
                        "post_release_bulk_density_kg_m3"
                    ),
                    "random_seed": imported_preparation.get("random_seed"),
                }
            )
        (paths["terrain"] / "terrain_preparation.json").write_text(
            json.dumps(preparation, indent=2, sort_keys=True) + "\n"
        )
        print(f"Imported settled terrain: {initial_state}")
        return
    runpy.run_path(str(project_root / "terraingeneration.py"), run_name="__main__")
    if not target.exists():
        raise RuntimeError(f"Terrain generation did not create {target}")


def run_penetration(project_root: Path, config: Any, paths: dict[str, Path], overwrite: bool) -> None:
    if not settled_terrain_path(paths["terrain"]).exists():
        raise RuntimeError("Settled terrain is missing; run the terrain stage first")
    if paths["penetration"].exists():
        if overwrite:
            shutil.rmtree(paths["penetration"])
        else:
            raise RuntimeError("Penetration output exists; use --overwrite to replace it")
    runpy.run_path(str(project_root / "penetration.py"), run_name="__main__")


def contact_force(path: Path) -> tuple[float, int]:
    force_z = 0.0
    contacts = 0
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("contact_type") != "SM":
                continue
            force_z += float(row["f_z"])
            contacts += 1
    return abs(force_z), contacts


def binned_profile(points: list[tuple[float, float]], bin_width_m: float = 0.005):
    bins: dict[int, list[float]] = {}
    for depth, pressure in points:
        if depth <= 0:
            continue
        index = round(depth / bin_width_m)
        bins.setdefault(index, []).append(pressure)
    return [
        (index * bin_width_m, statistics.median(values), len(values))
        for index, values in sorted(bins.items())
        if values
    ]


def score_profile(
    predicted: list[tuple[float, float]], observed_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    predicted_points = [(depth * 1000.0, pressure) for depth, pressure in predicted]
    observed = [
        (float(row["depth_mm"]), float(row["mean_kpa"]))
        for row in observed_rows
        if float(row["depth_mm"]) <= 100.0
    ]
    predictions = [(depth, interpolate(predicted_points, depth)) for depth, _ in observed]
    log_errors = [
        math.log((prediction + 1.0) / (measurement + 1.0))
        for (depth, prediction), (_, measurement) in zip(predictions, observed)
    ]
    predicted_fit = linear_fit(predictions)
    observed_fit = linear_fit(observed)
    predicted_q100 = interpolate(predicted_points, 100.0)
    observed_q100 = interpolate(observed, 100.0)
    log_rmse = math.sqrt(statistics.fmean(error**2 for error in log_errors))
    q100_log_error = abs(math.log((predicted_q100 + 1.0) / (observed_q100 + 1.0)))
    slope_log_error = abs(
        math.log(
            (abs(predicted_fit["slope_kpa_per_mm"]) + 0.1)
            / (abs(observed_fit["slope_kpa_per_mm"]) + 0.1)
        )
    )
    return {
        "score_lower_is_better": 0.5 * log_rmse + 0.3 * q100_log_error + 0.2 * slope_log_error,
        "profile_log_rmse": log_rmse,
        "q_100mm_predicted_kpa": predicted_q100,
        "q_100mm_observed_kpa": observed_q100,
        "q_100mm_ratio_predicted_to_observed": predicted_q100 / observed_q100,
        "predicted_fit_10_to_100mm": predicted_fit,
        "observed_fit_10_to_100mm": observed_fit,
        "comparison": [
            {"depth_mm": depth, "predicted_kpa": prediction, "observed_kpa": measurement}
            for (depth, prediction), (_, measurement) in zip(predictions, observed)
        ],
    }


def analyze(case: dict[str, Any], paths: dict[str, Path], project_root: Path) -> dict[str, Any]:
    kinematics_path = paths["penetration"] / "penetration_kinematics.csv"
    if not kinematics_path.exists():
        raise RuntimeError(f"Missing penetration kinematics: {kinematics_path}")
    frames = {}
    with kinematics_path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            frames[int(row["frame"])] = row
    area = float(case["probe"].get("base_area_m2", math.pi * (float(case["probe"]["base_diameter_m"]) / 2.0) ** 2))
    raw = []
    tracker_forces_available = all(
        "contact_force_z_n" in row and row["contact_force_z_n"] != ""
        for row in frames.values()
    )
    if tracker_forces_available:
        for frame, row in sorted(frames.items()):
            force = abs(float(row["contact_force_z_n"]))
            depth = float(row["tip_depth_m"])
            raw.append((depth, force, force / area / 1000.0, None))
    else:
        for contact_path in sorted((paths["penetration"] / "contact forces").glob("cpt_contact_*.csv")):
            match = re.search(r"(\d+)$", contact_path.stem)
            if not match or int(match.group(1)) not in frames:
                continue
            frame = int(match.group(1))
            force, contacts = contact_force(contact_path)
            depth = float(frames[frame]["tip_depth_m"])
            raw.append((depth, force, force / area / 1000.0, contacts))
    if not raw:
        raise RuntimeError("No contact-force samples were produced")
    profile = binned_profile([(depth, pressure) for depth, _, pressure, _ in raw])
    response_path = paths["penetration"] / "cpt_response.csv"
    with response_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["depth_m", "force_n", "cone_index_kpa", "sm_contacts"])
        writer.writerows(raw)
    profile_path = paths["penetration"] / "cpt_profile_5mm.csv"
    with profile_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["depth_m", "median_cone_index_kpa", "samples"])
        writer.writerows(profile)

    result = {
        "case_id": case["case_id"],
        "status": "PASS_SOFTWARE_INTEGRITY",
        "samples": len(raw),
        "force_source": "probe_tracker_contact_acceleration" if tracker_forces_available else "summed_sm_contact_files",
        "maximum_contacts_in_sample": max(
            (item[3] for item in raw if item[3] is not None), default=None
        ),
        "maximum_force_n": max(item[1] for item in raw),
        "maximum_cone_index_kpa": max(item[2] for item in raw),
        "profile_path": str(profile_path),
        "response_path": str(response_path),
    }
    preparation_path = paths["terrain"] / "terrain_preparation.json"
    if preparation_path.exists():
        preparation = json.loads(preparation_path.read_text())
        target_density = preparation.get("target_bulk_density_kg_m3")
        achieved_density = preparation.get("post_release_bulk_density_kg_m3")
        if target_density is not None and achieved_density is not None:
            density_ratio = float(achieved_density) / float(target_density)
            tolerance = float(case["terrain"].get("bulk_density_tolerance_fraction", 0.03))
            density_pass = abs(density_ratio - 1.0) <= tolerance
            result["density_gate"] = {
                "status": "PASS_DENSITY" if density_pass else "REJECT_DENSITY_MISMATCH",
                "target_bulk_density_kg_m3": target_density,
                "achieved_bulk_density_kg_m3": achieved_density,
                "achieved_to_target_ratio": density_ratio,
                "tolerance_fraction": tolerance,
            }
            if not density_pass:
                result["status"] = "REJECT_DENSITY_MISMATCH"
    reference = case.get("physical_reference", {})
    if reference.get("reference_json"):
        reference_path = resolve_path(project_root, Path(case["_manifest_path"]), reference["reference_json"])
        reference_data = json.loads(reference_path.read_text())
        target_state = reference.get("target_state", "out_track")
        predicted = [(depth, pressure) for depth, pressure, _ in profile]
        try:
            result["calibration"] = {
                "target_state": target_state,
                **score_profile(predicted, reference_data["states"][target_state]["rows"]),
            }
        except ValueError as exc:
            if result["status"].startswith("PASS"):
                result["status"] = "PASS_SOFTWARE_INTEGRITY_INCOMPLETE_DEPTH"
            result["calibration_error"] = str(exc)
    (paths["penetration"] / "cpt_run_health.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run and score a GRASP CPT DEM case")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--stage", choices=("preflight", "terrain", "penetration", "analyze", "all"), default="preflight"
    )
    parser.add_argument("--output-root", type=Path, default=Path("cpt_case_runs"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent
    case_path = args.manifest.resolve()
    case, paths, report = preflight_case(case_path, project_root, args.output_root.resolve())
    case["_manifest_path"] = str(case_path)
    print(f"Preflight: {report['status']} - {case['case_id']}")
    print(f"Particles (estimated): {report['estimated_initial_particle_count']:,}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for failure in report["failures"]:
        print(f"ERROR: {failure}")
    if report["failures"]:
        return 2
    if args.stage == "preflight":
        return 0
    if args.stage == "analyze":
        print(json.dumps(analyze(case, paths, project_root), indent=2))
        return 0
    require_deme()
    config_namespace = runpy.run_path(str(project_root / "config.py"))
    config = SimpleNamespace(**config_namespace)
    apply_config(config, case, paths)
    sys.modules["config"] = config
    (paths["case_dir"] / "runtime_environment.json").write_text(
        json.dumps(runtime_environment(), indent=2, sort_keys=True) + "\n"
    )
    if args.stage in ("terrain", "all"):
        run_terrain(project_root, config, paths, args.overwrite)
    if args.stage in ("penetration", "all"):
        run_penetration(project_root, config, paths, args.overwrite)
        print(json.dumps(analyze(case, paths, project_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
