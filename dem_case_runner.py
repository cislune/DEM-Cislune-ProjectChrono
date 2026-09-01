#!/usr/bin/env python3
"""Manifest-driven OBJ preflight and PyDEME case runner."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any


UNIT_TO_M = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "mm": 1e-3,
    "millimeter": 1e-3,
    "millimeters": 1e-3,
    "cm": 1e-2,
    "centimeter": 1e-2,
    "centimeters": 1e-2,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
}


class CaseError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(project_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def command_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            command, text=True, stderr=subprocess.DEVNULL, timeout=10
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def runtime_environment() -> dict[str, Any]:
    try:
        import DEME

        deme_path = str(Path(DEME.__file__).resolve())
        deme_version = getattr(DEME, "__version__", None)
    except Exception as exc:  # Runtime metadata must survive a partially broken environment.
        deme_path = None
        deme_version = None
        deme_error = f"{type(exc).__name__}: {exc}"
    else:
        deme_error = None

    gpu = command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ]
    )
    return {
        "python": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "platform": platform.platform(),
        "deme_path": deme_path,
        "deme_version": deme_version,
        "deme_import_error": deme_error,
        "cuda_home": os.environ.get("CUDA_HOME"),
        "container_image_digest": os.environ.get("GRASP_DEM_CONTAINER_DIGEST"),
        "gpu": gpu.splitlines() if gpu else [],
    }


def load_case(path: Path) -> dict[str, Any]:
    try:
        case = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseError(f"Cannot read case manifest {path}: {exc}") from exc

    if case.get("schema_version") != 1:
        raise CaseError("Only schema_version 1 is supported")
    for key in ("case_id", "wheel", "test", "terrain"):
        if key not in case:
            raise CaseError(f"Missing required manifest field: {key}")
    if not isinstance(case["case_id"], str) or not case["case_id"].strip():
        raise CaseError("case_id must be a non-empty string")
    return case


def resolve_obj_path(project_root: Path, manifest_path: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    candidates = [raw] if raw.is_absolute() else [project_root / raw, manifest_path.parent / raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise CaseError(f"Wheel OBJ not found: {value}")


def axis_vector(spec: str) -> tuple[float, float, float]:
    value = spec.strip().lower()
    sign = -1.0 if value.startswith("-") else 1.0
    axis = value[1:] if value[:1] in "+-" else value
    if axis not in {"x", "y", "z"}:
        raise CaseError(f"Invalid axis specification: {spec}")
    vector = [0.0, 0.0, 0.0]
    vector[{"x": 0, "y": 1, "z": 2}[axis]] = sign
    return tuple(vector)


def axis_transform(source_axes: dict[str, str]) -> tuple[list[tuple[float, float, float]], float]:
    try:
        rows = [
            axis_vector(source_axes["travel"]),
            axis_vector(source_axes["axle"]),
            axis_vector(source_axes["up"]),
        ]
    except KeyError as exc:
        raise CaseError("source_axes must define travel, axle, and up") from exc

    used = [next(i for i, value in enumerate(row) if value) for row in rows]
    if len(set(used)) != 3:
        raise CaseError("travel, axle, and up must use three distinct source axes")

    a, b, c = rows
    determinant = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    return rows, determinant


def transform_xyz(
    xyz: tuple[float, float, float], rows: list[tuple[float, float, float]]
) -> tuple[float, float, float]:
    return tuple(sum(row[i] * xyz[i] for i in range(3)) for row in rows)


def parse_vertex_index(token: str, vertex_count: int) -> int:
    raw = token.split("/", 1)[0]
    if not raw:
        raise CaseError(f"OBJ face has an empty vertex index: {token}")
    index = int(raw)
    resolved = index - 1 if index > 0 else vertex_count + index
    if resolved < 0 or resolved >= vertex_count:
        raise CaseError(f"OBJ vertex index out of range: {index}")
    return resolved


def inspect_obj(path: Path) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    edges: Counter[tuple[int, int]] = Counter()
    faces = 0
    non_triangles = 0
    degenerate_faces = 0

    with path.open(errors="strict") as stream:
        for line_number, line in enumerate(stream, 1):
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "v" and len(parts) >= 4:
                try:
                    vertex = tuple(float(value) for value in parts[1:4])
                except ValueError as exc:
                    raise CaseError(f"Invalid vertex on line {line_number}") from exc
                if not all(math.isfinite(value) for value in vertex):
                    raise CaseError(f"Non-finite vertex on line {line_number}")
                vertices.append(vertex)
            elif parts[0] == "f":
                if len(parts) < 4:
                    raise CaseError(f"Face has fewer than three vertices on line {line_number}")
                indices = [parse_vertex_index(token, len(vertices)) for token in parts[1:]]
                faces += 1
                non_triangles += len(indices) != 3
                degenerate_faces += len(set(indices)) != len(indices)
                for start, end in zip(indices, indices[1:] + indices[:1]):
                    edges[tuple(sorted((start, end)))] += 1

    if not vertices:
        raise CaseError(f"OBJ has no vertices: {path}")
    if not faces:
        raise CaseError(f"OBJ has no faces: {path}")

    minimum = [min(vertex[i] for vertex in vertices) for i in range(3)]
    maximum = [max(vertex[i] for vertex in vertices) for i in range(3)]
    extents = [maximum[i] - minimum[i] for i in range(3)]
    edge_use = Counter(edges.values())
    boundary_edges = edge_use.get(1, 0)
    nonmanifold_edges = sum(count for uses, count in edge_use.items() if uses > 2)

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "vertices": len(vertices),
        "faces": faces,
        "non_triangular_faces": non_triangles,
        "degenerate_faces": degenerate_faces,
        "bounds_min_m": minimum,
        "bounds_max_m": maximum,
        "extents_m": extents,
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "watertight_two_manifold": boundary_edges == 0 and nonmanifold_edges == 0,
    }


def normalize_obj(
    source: Path,
    destination: Path,
    units: str,
    source_axes: dict[str, str],
) -> None:
    try:
        scale = UNIT_TO_M[units.strip().lower()]
    except KeyError as exc:
        raise CaseError(f"Unsupported OBJ unit: {units}") from exc
    rows, determinant = axis_transform(source_axes)
    lines = source.read_text().splitlines()

    transformed_vertices: list[tuple[float, float, float]] = []
    for line in lines:
        parts = line.strip().split()
        if parts and parts[0] == "v" and len(parts) >= 4:
            xyz = tuple(float(value) for value in parts[1:4])
            transformed = transform_xyz(xyz, rows)
            transformed_vertices.append(tuple(value * scale for value in transformed))
    if not transformed_vertices:
        raise CaseError(f"OBJ has no vertices: {source}")

    minimum = [min(vertex[i] for vertex in transformed_vertices) for i in range(3)]
    maximum = [max(vertex[i] for vertex in transformed_vertices) for i in range(3)]
    center = [(minimum[i] + maximum[i]) / 2.0 for i in range(3)]

    destination.parent.mkdir(parents=True, exist_ok=True)
    vertex_cursor = 0
    output = [
        "# Normalized by dem_case_runner.py",
        f"# Source SHA-256: {sha256_file(source)}",
        "# Frame: +X travel, +Y axle, +Z up; units: meters; origin: bounding-box center",
    ]
    for line in lines:
        parts = line.strip().split()
        if parts and parts[0] == "v" and len(parts) >= 4:
            vertex = transformed_vertices[vertex_cursor]
            vertex_cursor += 1
            extras = " " + " ".join(parts[4:]) if len(parts) > 4 else ""
            output.append(
                "v " + " ".join(f"{vertex[i] - center[i]:.12g}" for i in range(3)) + extras
            )
        elif parts and parts[0] == "vn" and len(parts) >= 4:
            normal = transform_xyz(tuple(float(value) for value in parts[1:4]), rows)
            normal = tuple(determinant * value for value in normal)
            length = math.sqrt(sum(value * value for value in normal))
            if length:
                normal = tuple(value / length for value in normal)
            output.append("vn " + " ".join(f"{value:.12g}" for value in normal))
        else:
            output.append(line)
    destination.write_text("\n".join(output) + "\n")


def relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / expected


def estimated_particle_count(terrain: dict[str, Any]) -> int:
    radius = float(terrain["base_particle_radius_m"])
    fill_fraction = float(terrain.get("initial_solid_fraction", 0.55))
    fill_height = float(terrain.get("initial_fill_height_m", terrain["bed_depth_m"]))
    volume = (
        float(terrain["bin_travel_length_m"])
        * float(terrain["bin_width_m"])
        * fill_height
    )
    sphere_volume = (4.0 / 3.0) * math.pi * radius**3
    return max(1, round(fill_fraction * volume / sphere_volume))


def csv_data_rows(path: Path) -> int:
    with path.open(newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def preflight_case(
    case_path: Path, project_root: Path, output_root: Path
) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    case = load_case(case_path)
    case_dir = output_root / case["case_id"]
    normalized_obj = case_dir / "input" / "wheel.normalized.obj"
    source_obj = resolve_obj_path(project_root, case_path, case["wheel"]["obj"])
    design_obj = None
    design_obj_sha256 = None
    if case["wheel"].get("design_obj"):
        design_obj = resolve_obj_path(project_root, case_path, case["wheel"]["design_obj"])
        design_obj_sha256 = sha256_file(design_obj)
    normalize_obj(
        source_obj,
        normalized_obj,
        case["wheel"].get("obj_units", "m"),
        case["wheel"].get(
            "source_axes", {"travel": "+x", "axle": "+y", "up": "+z"}
        ),
    )

    mesh = inspect_obj(normalized_obj)
    extents = mesh["extents_m"]
    measured_envelope_radius = max(extents[0], extents[2]) / 2.0
    measured_width = extents[1]
    expected_envelope_radius = float(case["wheel"]["envelope_radius_m"])
    expected_width = float(case["wheel"]["width_m"])
    tolerance = float(case["wheel"].get("dimension_tolerance_fraction", 0.03))

    failures: list[str] = []
    warnings: list[str] = []
    if mesh["non_triangular_faces"]:
        failures.append(f"mesh has {mesh['non_triangular_faces']} non-triangular faces")
    if mesh["degenerate_faces"]:
        failures.append(f"mesh has {mesh['degenerate_faces']} degenerate faces")
    if not mesh["watertight_two_manifold"]:
        failures.append(
            f"mesh is not watertight two-manifold: {mesh['boundary_edges']} boundary and "
            f"{mesh['nonmanifold_edges']} nonmanifold edges"
        )
    if relative_error(measured_envelope_radius, expected_envelope_radius) > tolerance:
        failures.append(
            f"mesh envelope radius {measured_envelope_radius:.6g} m does not match "
            f"manifest {expected_envelope_radius:.6g} m"
        )
    if relative_error(measured_width, expected_width) > tolerance:
        failures.append(
            f"mesh width {measured_width:.6g} m does not match manifest {expected_width:.6g} m"
        )

    radial_asymmetry = abs(extents[0] - extents[2]) / max(extents[0], extents[2])
    if radial_asymmetry > 0.10:
        warnings.append(
            f"travel/up mesh extents differ by {radial_asymmetry:.1%}; verify wheel axis and geometry"
        )
    if case.get("model_status") != "calibrated_validation":
        warnings.append(
            f"model_status is {case.get('model_status', 'unspecified')}; results are not an absolute validation prediction"
        )
    if design_obj and design_obj != source_obj:
        warnings.append(
            "simulation uses a derived collision mesh; preserve the design OBJ hash and verify dimensional tolerance"
        )

    test = case["test"]
    terrain = case["terrain"]
    mode = test.get("kinematics_mode", "fixed_angular_speed")
    if mode not in {"fixed_angular_speed", "fixed_linear_speed"}:
        failures.append(f"unsupported kinematics_mode: {mode}")
    slips = [float(value) for value in test["slip_ratios"]]
    if any(value < 0.0 or value >= 1.0 for value in slips):
        failures.append("slip_ratios must be in the interval [0, 1)")
    if int(test.get("passes", 1)) < 1:
        failures.append("passes must be at least 1")

    gravity = float(test["gravity_m_s2"])
    normal_load = float(test["normal_load_n"])
    linear_speed = float(test["linear_speed_m_s"])
    duration = float(test["duration_s"])
    rolling_radius = float(case["wheel"]["rolling_radius_m"])
    if gravity <= 0 or normal_load <= 0 or linear_speed < 0 or duration <= 0:
        failures.append("gravity, normal load, and duration must be positive; speed cannot be negative")
    if rolling_radius <= 0 or rolling_radius > measured_envelope_radius:
        failures.append("rolling_radius_m must be positive and no larger than the mesh envelope radius")

    particle_radius = float(terrain["base_particle_radius_m"])
    bin_travel = float(terrain["bin_travel_length_m"])
    bin_width = float(terrain["bin_width_m"])
    bed_depth = float(terrain["bed_depth_m"])
    travel_distance = linear_speed * duration
    required_travel = 2.0 * measured_envelope_radius + travel_distance + 8.0 * particle_radius
    required_width = measured_width + 8.0 * particle_radius
    if particle_radius <= 0:
        failures.append("base_particle_radius_m must be positive")
    if bin_travel < required_travel:
        failures.append(
            f"bin travel length {bin_travel:.6g} m is below the {required_travel:.6g} m "
            "minimum for wheel diameter, commanded travel, and particle clearance"
        )
    if bin_width < required_width:
        failures.append(
            f"bin width {bin_width:.6g} m is below the {required_width:.6g} m minimum "
            "for wheel width and particle clearance"
        )
    if bed_depth < max(8.0 * particle_radius, 0.25 * measured_envelope_radius):
        warnings.append("bed depth is shallow relative to particle size or wheel radius; boundary effects may dominate")

    material_density = float(terrain["particle_density_kg_m3"])
    if material_density < 1800:
        warnings.append(
            "particle_density_kg_m3 is below typical mineral grain density; do not substitute settled bulk density for particle material density"
        )
    if float(terrain["coefficient_of_restitution"]) > 0.5:
        warnings.append("particle restitution exceeds 0.5; verify against calibration because energetic rebound can destabilize fine-particle runs")
    if float(terrain["wheel_restitution"]) > 0.5:
        warnings.append("wheel restitution exceeds 0.5; verify against calibration")

    initial_state_path = None
    if terrain.get("initial_state_csv"):
        try:
            initial_state_path = resolve_obj_path(
                project_root, case_path, terrain["initial_state_csv"]
            )
            case["_resolved_initial_state_csv"] = str(initial_state_path)
        except CaseError as exc:
            failures.append(str(exc).replace("Wheel OBJ", "Initial terrain state"))

    average_contact_limit = float(case.get("solver", {}).get("error_out_avg_contacts", 100.0))
    if average_contact_limit > 100.0:
        warnings.append(
            f"average-contact guard is raised to {average_contact_limit:g} for detailed mesh contact; retain velocity and output-integrity rejection gates"
        )

    estimated_particles = (
        csv_data_rows(initial_state_path)
        if initial_state_path
        else estimated_particle_count(terrain) if particle_radius > 0 else 0
    )
    if estimated_particles > 2_000_000:
        warnings.append(
            f"estimated initial particle count is {estimated_particles:,}; run a coarser checkout before this resolution"
        )

    output = case.get("output", {})
    write_every = int(output.get("wheel_write_every_n_frames", 100))
    frame_time = float(output.get("wheel_frame_time_s", 1e-3))
    if write_every < 1 or frame_time <= 0:
        failures.append("output frame time and write cadence must be positive")

    reference_path = None
    reference_sha256 = None
    reference_value = case.get("physical_reference", {}).get("reference_json")
    if reference_value:
        try:
            reference_path = resolve_obj_path(project_root, case_path, reference_value)
        except CaseError:
            failures.append(f"physical reference file not found: {reference_value}")
        else:
            reference_sha256 = sha256_file(reference_path)

    report = {
        "status": "FAIL" if failures else "PASS",
        "case_id": case["case_id"],
        "model_status": case.get("model_status"),
        "project_git_revision": git_revision(project_root),
        "source_obj": str(source_obj),
        "source_obj_sha256": sha256_file(source_obj),
        "design_obj": str(design_obj) if design_obj else str(source_obj),
        "design_obj_sha256": design_obj_sha256 or sha256_file(source_obj),
        "normalized_obj": str(normalized_obj),
        "mesh": mesh,
        "measured_envelope_radius_m": measured_envelope_radius,
        "measured_width_m": measured_width,
        "rolling_radius_m": float(case["wheel"]["rolling_radius_m"]),
        "derived": {
            "commanded_travel_m": travel_distance,
            "minimum_bin_travel_length_m": required_travel,
            "minimum_bin_width_m": required_width,
            "estimated_initial_particle_count": estimated_particles,
            "predicted_wheel_frames": math.ceil(duration / frame_time),
            "predicted_written_frames": math.ceil(duration / frame_time / write_every),
            "angular_speed_rad_s_by_slip": {
                f"{slip:.6g}": (
                    linear_speed / ((1.0 - slip) * rolling_radius)
                    if mode == "fixed_linear_speed"
                    else float(test.get("angular_speed_rad_s", linear_speed / rolling_radius))
                )
                for slip in slips
            },
        },
        "physical_reference_path": str(reference_path) if reference_path else None,
        "physical_reference_sha256": reference_sha256,
        "initial_state_path": str(initial_state_path) if initial_state_path else None,
        "initial_state_sha256": sha256_file(initial_state_path) if initial_state_path else None,
        "failures": failures,
        "warnings": warnings,
    }

    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "preflight.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    frozen = dict(case)
    frozen["provenance"] = {
        "manifest_path": str(case_path.resolve()),
        "manifest_sha256": sha256_file(case_path),
        "source_obj_path": str(source_obj),
        "source_obj_sha256": report["source_obj_sha256"],
        "design_obj_path": report["design_obj"],
        "design_obj_sha256": report["design_obj_sha256"],
        "normalized_obj_sha256": mesh["sha256"],
        "physical_reference_path": str(reference_path) if reference_path else None,
        "physical_reference_sha256": reference_sha256,
        "initial_state_path": report["initial_state_path"],
        "initial_state_sha256": report["initial_state_sha256"],
        "project_git_revision": report["project_git_revision"],
    }
    (case_dir / "frozen_case.json").write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")

    paths = {
        "case_dir": case_dir,
        "normalized_obj": normalized_obj,
        "terrain": case_dir / "terrain",
        "wheel": case_dir / "wheel",
        "compaction": case_dir / "compaction",
    }
    return case, paths, report


def apply_case_config(config: Any, case: dict[str, Any], paths: dict[str, Path]) -> None:
    import numpy as np

    wheel = case["wheel"]
    test = case["test"]
    terrain = case["terrain"]

    gravity = float(test["gravity_m_s2"])
    rolling_radius = float(wheel["rolling_radius_m"])
    envelope_radius = float(wheel["envelope_radius_m"])
    width = float(wheel["width_m"])
    effective_mass = float(wheel["effective_mass_kg"])
    normal_load = float(test["normal_load_n"])

    config.USE_DEMO_WHEEL_st = False
    config.G_MAG_st = gravity
    config.GRAVITATIONAL_ACCELERATION_st = [0.0, 0.0, -gravity]
    config.WHEEL_RAD_st = envelope_radius
    config.WHEEL_ROLLING_RADIUS_st = rolling_radius
    config.WHEEL_ENVELOPE_RADIUS_st = envelope_radius
    config.WHEEL_WIDTH_st = width
    config.WHEEL_MASS_st = effective_mass
    config.WHEEL_WEIGHT_st = effective_mass * gravity
    config.WHEEL_IYY_st = effective_mass * envelope_radius**2 / 2.0
    config.WHEEL_IXX_st = effective_mass * (3.0 * envelope_radius**2 + width**2) / 12.0
    config.WHEEL_OBJ_FILE_st = str(paths["normalized_obj"])
    config.TARGET_NORMAL_FORCE_st = normal_load
    config.SUPPLEMENTARY_FORCE_st = normal_load - config.WHEEL_WEIGHT_st

    config.WHEEL_KINEMATICS_MODE_st = test.get(
        "kinematics_mode", "fixed_angular_speed"
    )
    config.WHEEL_LINEAR_VEL_st = float(test["linear_speed_m_s"])
    config.WHEEL_ANG_VEL_st = float(
        test.get("angular_speed_rad_s", config.WHEEL_LINEAR_VEL_st / rolling_radius)
    )
    config.SLIP_VALUES_st = np.array([float(value) for value in test["slip_ratios"]])
    config.TRIAL_RUN_TIME_SLIP_SINKAGE_st = float(test["duration_s"])

    config.BASE_TERRAIN_RAD_st = float(terrain["base_particle_radius_m"])
    config.TERRAIN_PARTICLE_SHAPE_st = terrain.get("particle_shape", "sphere")
    config.TERRAIN_DENSITY_st = float(terrain["particle_density_kg_m3"])
    config.E_st = float(terrain["youngs_modulus_pa"])
    config.NU_st = float(terrain["poissons_ratio"])
    config.COR_st = float(terrain["coefficient_of_restitution"])
    config.MU_st = float(terrain["particle_friction"])
    config.CRR_st = float(terrain["rolling_resistance"])
    config.COHESION_st = float(terrain["cohesion"])
    config.MU_contact_wheel_st = float(terrain["wheel_friction"])
    config.COR_contact_wheel_st = float(terrain["wheel_restitution"])
    config.COHESION_contact_wheel_st = float(terrain["wheel_cohesion"])
    config.STEP_SIZE_st = float(terrain["time_step_s"])
    config.WIDTH_st = float(terrain["bin_travel_length_m"])
    config.LENGTH_st = float(terrain["bin_width_m"])
    config.DEPTH_st = float(terrain["bed_depth_m"])
    initial_fill_height = float(terrain.get("initial_fill_height_m", config.DEPTH_st))
    config.FULL_HEIGHT_st = -config.DEPTH_st / 2.0 + initial_fill_height

    output = case.get("output", {})
    solver = case.get("solver", {})
    config.MAX_VELOCITY_st = float(solver.get("max_velocity_m_s", 30.0))
    config.ERROR_OUT_VELOCITY_st = float(solver.get("error_out_velocity_m_s", 30.0))
    config.MAX_TRIANGLES_IN_BIN_st = int(solver.get("max_triangles_in_bin", 100000))
    config.ERROR_OUT_AVG_CONTACTS_st = float(solver.get("error_out_avg_contacts", 100.0))
    config.TERRAIN_RANDOM_SEED_st = int(terrain.get("random_seed", 77))
    config.TERRAIN_SETTLE_TIME_S_st = float(terrain.get("settle_time_s", 1.0))
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
            terrain.get("compression_speed_m_s", 0.03)
        )
        config.TERRAIN_COMPRESSION_MAX_TIME_S_st = float(
            terrain.get("compression_max_time_s", 12.0)
        )
        config.TERRAIN_COMPRESSION_RELEASE_MARGIN_st = float(
            terrain.get("compression_release_margin", 0.03)
        )
        config.TERRAIN_POST_COMPRESSION_RELAX_S_st = float(
            terrain.get("post_compression_relax_s", 0.2)
        )
    config.TERRAIN_FRAME_TIME_S_st = float(output.get("terrain_frame_time_s", 1e-3))
    config.TERRAIN_WRITE_EVERY_N_FRAMES_st = int(
        output.get("terrain_write_every_n_frames", 100)
    )
    config.TERRAIN_WRITE_MOTION_st = bool(output.get("write_terrain_settling_motion", False))
    config.TERRAIN_INITIAL_STATE_CSV_st = case.get("_resolved_initial_state_csv")
    config.TERRAIN_IMPORTED_PREPARATION_st = case.get("shared_sample_preparation")
    config.SLIP_FRAME_TIME_S_st = float(output.get("wheel_frame_time_s", 1e-3))
    config.SLIP_WRITE_EVERY_N_FRAMES_st = int(
        output.get("wheel_write_every_n_frames", 100)
    )
    config.SLIP_WRITE_TERRAIN_st = bool(output.get("write_wheel_terrain_motion", True))
    config.SLIP_WRITE_WHEEL_st = bool(output.get("write_wheel_mesh_motion", True))
    config.SLIP_WRITE_CONTACT_st = bool(output.get("write_contact_forces", True))

    config.SPHERE_TERRAIN_GEN_OUT_DIR = str(paths["terrain"])
    config.SLIP_SINKAGE_OUT_DIR = str(paths["wheel"])
    config.COMPACTION_OUT_DIR = str(paths["compaction"])
    config.WHEEL_LABEL_st = case["case_id"]


def require_deme() -> None:
    try:
        __import__("DEME")
    except Exception as exc:
        raise RuntimeError(
            "DEME is not importable. Run through run_dem_case_docker.sh so the pinned "
            "container and CUDA_HOME are supplied. "
            f"Original error: {type(exc).__name__}: {exc}"
        ) from exc


def settled_terrain_path(root: Path) -> Path:
    return root / "settled terrain data" / "settled_terrain_data.csv"


def slip_label(slip: float) -> str:
    return f"{slip:.6f}".rstrip("0").rstrip(".")


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
            for key in (
                "source_preparation_path",
                "source_preparation_sha256",
                "target_bulk_density_kg_m3",
                "post_release_bulk_density_kg_m3",
            ):
                if key in imported_preparation:
                    preparation[key] = imported_preparation[key]
        (paths["terrain"] / "terrain_preparation.json").write_text(
            json.dumps(preparation, indent=2, sort_keys=True) + "\n"
        )
        print(f"Imported settled terrain: {initial_state}")
        return
    config.SPHERE_TERRAIN_GEN_OUT_DIR = str(paths["terrain"])
    runpy.run_path(str(project_root / "terraingeneration.py"), run_name="__main__")
    if not target.exists():
        raise RuntimeError(f"Terrain generation did not create {target}")


def run_wheel_passes(
    project_root: Path,
    config: Any,
    case: dict[str, Any],
    paths: dict[str, Path],
    overwrite: bool,
) -> None:
    import numpy as np

    original_baseline = settled_terrain_path(paths["terrain"])
    if not original_baseline.exists():
        raise RuntimeError(f"Settled terrain is missing: {original_baseline}")

    passes = int(case["test"].get("passes", 1))
    for slip in [float(value) for value in case["test"]["slip_ratios"]]:
        baseline = original_baseline
        label = slip_label(slip)
        for pass_number in range(1, passes + 1):
            pass_root = paths["wheel"] / f"slip_{label}" / f"pass_{pass_number:02d}"
            if pass_root.exists():
                if overwrite:
                    shutil.rmtree(pass_root)
                else:
                    raise RuntimeError(
                        f"Wheel output already exists: {pass_root}; use --overwrite to replace it"
                    )

            input_root = paths["case_dir"] / "cumulative_inputs" / f"slip_{label}" / f"pass_{pass_number:02d}"
            input_target = settled_terrain_path(input_root)
            input_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(baseline, input_target)

            config.SPHERE_TERRAIN_GEN_OUT_DIR = str(input_root)
            config.SLIP_SINKAGE_OUT_DIR = str(pass_root)
            config.SLIP_VALUES_st = np.array([slip])
            runpy.run_path(str(project_root / "slipsinkage.py"), run_name="__main__")

            final_state = (
                pass_root
                / "Trial 1"
                / f"Slip {label}"
                / "settled data"
                / f"slip_sinkage_settled_data_slip_{label}.csv"
            )
            if not final_state.exists():
                raise RuntimeError(f"Wheel simulation did not create {final_state}")
            baseline = final_state


def run_compaction(
    project_root: Path,
    config: Any,
    case: dict[str, Any],
    paths: dict[str, Path],
    overwrite: bool,
) -> None:
    passes = int(case["test"].get("passes", 1))
    for slip in [float(value) for value in case["test"]["slip_ratios"]]:
        label = slip_label(slip)
        for pass_number in range(1, passes + 1):
            input_root = paths["case_dir"] / "cumulative_inputs" / f"slip_{label}" / f"pass_{pass_number:02d}"
            pass_root = paths["wheel"] / f"slip_{label}" / f"pass_{pass_number:02d}"
            output_root = paths["compaction"] / f"slip_{label}" / f"pass_{pass_number:02d}"
            if not pass_root.exists():
                raise RuntimeError(f"Wheel output is missing: {pass_root}")
            if output_root.exists():
                if overwrite:
                    shutil.rmtree(output_root)
                else:
                    raise RuntimeError(
                        f"Compaction output already exists: {output_root}; use --overwrite to replace it"
                    )
            config.SPHERE_TERRAIN_GEN_OUT_DIR = str(input_root)
            config.SLIP_SINKAGE_OUT_DIR = str(pass_root)
            config.COMPACTION_OUT_DIR = str(output_root)
            config.WHEEL_LABEL_st = f"{case['case_id']} pass {pass_number}"
            runpy.run_path(str(project_root / "compaction.py"), run_name="__main__")


def print_preflight(report: dict[str, Any]) -> None:
    print(f"Preflight: {report['status']} - {report['case_id']}")
    print(f"OBJ SHA-256: {report['source_obj_sha256']}")
    print(
        "Mesh: "
        f"{report['mesh']['vertices']} vertices, {report['mesh']['faces']} faces, "
        f"radius {report['measured_envelope_radius_m']:.6g} m, "
        f"width {report['measured_width_m']:.6g} m"
    )
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for failure in report["failures"]:
        print(f"ERROR: {failure}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an arbitrary wheel OBJ and run a frozen PyDEME case"
    )
    parser.add_argument("manifest", type=Path, help="JSON case manifest")
    parser.add_argument(
        "--stage",
        choices=("preflight", "terrain", "wheel", "compaction", "all"),
        default="preflight",
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("case_runs"), help="case output root"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="replace outputs for the selected stage"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent
    case_path = args.manifest.resolve()
    output_root = args.output_root.resolve()
    case, paths, report = preflight_case(case_path, project_root, output_root)
    print_preflight(report)
    if report["failures"]:
        return 2
    if args.stage == "preflight":
        print(f"Frozen case: {paths['case_dir'] / 'frozen_case.json'}")
        return 0

    require_deme()
    (paths["case_dir"] / "runtime_environment.json").write_text(
        json.dumps(runtime_environment(), indent=2, sort_keys=True) + "\n"
    )
    sys.path.insert(0, str(project_root))
    import config

    apply_case_config(config, case, paths)
    if args.stage in {"terrain", "all"}:
        run_terrain(project_root, config, paths, args.overwrite)
    if args.stage in {"wheel", "all"}:
        run_wheel_passes(project_root, config, case, paths, args.overwrite)
    if args.stage in {"compaction", "all"}:
        run_compaction(project_root, config, case, paths, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
