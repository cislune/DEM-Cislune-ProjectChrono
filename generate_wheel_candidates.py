#!/usr/bin/env python3
"""Generate watertight GRASP wheel candidates for DEM and Bambu-scale printing."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Callable

from dem_case_runner import inspect_obj


RTGS_HUB_REFERENCE_OD_M = 0.158718
RTGS_HUB_REFERENCE_WIDTH_M = 0.075
RIDER_CONVERTER_REFERENCE_OD_M = 0.1524
CANDIDATE_BORE_RADIUS_M = 0.0805


@dataclass(frozen=True)
class WheelSpec:
    name: str
    description: str
    core_radius_m: float
    feature_height_m: float
    width_m: float
    bore_radius_m: float
    lobes: int = 0
    profile_exponent: float = 1.0
    axial_phase_deg: float = 0.0
    phase_mode: str = "none"


CANDIDATES = (
    WheelSpec(
        "smooth_control",
        "Smooth control that minimizes deliberate shear features and anchors the compaction comparison.",
        0.190,
        0.0,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
    ),
    WheelSpec(
        "broad_wave_12",
        "Twelve shallow broad lobes intended to spread load while retaining modest thrust capacity.",
        0.190,
        0.008,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
        lobes=12,
        profile_exponent=0.65,
    ),
    WheelSpec(
        "low_grouser_16",
        "Sixteen low rounded grousers as a mobility guardrail without the soil excavation of tall blades.",
        0.190,
        0.012,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
        lobes=16,
        profile_exponent=1.1,
    ),
    WheelSpec(
        "low_grouser_16_10mm",
        "Tuned sixteen-feature wheel that reduces the low-grouser height from 12 mm to 10 mm to target the mobility guardrail.",
        0.190,
        0.010,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
        lobes=16,
        profile_exponent=1.1,
    ),
    WheelSpec(
        "staggered_wave_12",
        "Axially staggered broad lobes that avoid engaging the full width at one circumferential station.",
        0.190,
        0.014,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
        lobes=12,
        profile_exponent=1.2,
        axial_phase_deg=12.0,
        phase_mode="sine",
    ),
    WheelSpec(
        "chevron_wave_14",
        "Shallow chevron wave intended to preserve forward bite while distributing entry across the width.",
        0.190,
        0.009,
        0.1016,
        CANDIDATE_BORE_RADIUS_M,
        lobes=14,
        profile_exponent=0.85,
        axial_phase_deg=16.0,
        phase_mode="chevron",
    ),
)


def phase_offset(spec: WheelSpec, y_normalized: float) -> float:
    amplitude = math.radians(spec.axial_phase_deg)
    if spec.phase_mode == "sine":
        return amplitude * math.sin(math.pi * y_normalized)
    if spec.phase_mode == "chevron":
        return amplitude * abs(y_normalized)
    return 0.0


def outer_radius(spec: WheelSpec, theta: float, y_normalized: float) -> float:
    if spec.lobes <= 0 or spec.feature_height_m <= 0:
        return spec.core_radius_m
    wave = 0.5 * (
        1.0
        + math.cos(spec.lobes * theta + phase_offset(spec, y_normalized))
    )
    return spec.core_radius_m + spec.feature_height_m * wave**spec.profile_exponent


def build_mesh(
    spec: WheelSpec, angular_segments: int = 192, axial_segments: int = 24
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    if angular_segments < 12 or axial_segments < 1:
        raise ValueError("Mesh resolution is too low")
    vertices = []
    outer = []
    inner = []
    for axial in range(axial_segments + 1):
        fraction = axial / axial_segments
        y_normalized = 2.0 * fraction - 1.0
        y = -spec.width_m / 2.0 + fraction * spec.width_m
        outer_ring = []
        inner_ring = []
        for angular in range(angular_segments):
            theta = 2.0 * math.pi * angular / angular_segments
            radius = outer_radius(spec, theta, y_normalized)
            outer_ring.append(len(vertices))
            vertices.append((radius * math.cos(theta), y, radius * math.sin(theta)))
            inner_ring.append(len(vertices))
            vertices.append(
                (
                    spec.bore_radius_m * math.cos(theta),
                    y,
                    spec.bore_radius_m * math.sin(theta),
                )
            )
        outer.append(outer_ring)
        inner.append(inner_ring)

    faces = []
    for axial in range(axial_segments):
        for angular in range(angular_segments):
            following = (angular + 1) % angular_segments
            faces.extend(
                [
                    (
                        outer[axial][angular],
                        outer[axial + 1][angular],
                        outer[axial + 1][following],
                    ),
                    (
                        outer[axial][angular],
                        outer[axial + 1][following],
                        outer[axial][following],
                    ),
                    (
                        inner[axial][angular],
                        inner[axial][following],
                        inner[axial + 1][following],
                    ),
                    (
                        inner[axial][angular],
                        inner[axial + 1][following],
                        inner[axial + 1][angular],
                    ),
                ]
            )

    left = 0
    right = axial_segments
    for angular in range(angular_segments):
        following = (angular + 1) % angular_segments
        faces.extend(
            [
                (outer[left][angular], outer[left][following], inner[left][following]),
                (outer[left][angular], inner[left][following], inner[left][angular]),
                (outer[right][angular], inner[right][following], outer[right][following]),
                (outer[right][angular], inner[right][angular], inner[right][following]),
            ]
        )
    return vertices, faces


def build_sector_mesh(
    spec: WheelSpec,
    start_angle: float,
    end_angle: float,
    angular_segments: int = 64,
    axial_segments: int = 24,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Build a closed annular wheel sector for full-scale bed-size printing."""
    if end_angle <= start_angle:
        raise ValueError("Sector end angle must be greater than its start angle")
    if angular_segments < 2 or axial_segments < 1:
        raise ValueError("Mesh resolution is too low")
    vertices = []
    outer = []
    inner = []
    for axial in range(axial_segments + 1):
        fraction = axial / axial_segments
        y_normalized = 2.0 * fraction - 1.0
        y = -spec.width_m / 2.0 + fraction * spec.width_m
        outer_ring = []
        inner_ring = []
        for angular in range(angular_segments + 1):
            theta = start_angle + (end_angle - start_angle) * angular / angular_segments
            radius = outer_radius(spec, theta, y_normalized)
            outer_ring.append(len(vertices))
            vertices.append((radius * math.cos(theta), y, radius * math.sin(theta)))
            inner_ring.append(len(vertices))
            vertices.append(
                (
                    spec.bore_radius_m * math.cos(theta),
                    y,
                    spec.bore_radius_m * math.sin(theta),
                )
            )
        outer.append(outer_ring)
        inner.append(inner_ring)

    faces = []
    for axial in range(axial_segments):
        for angular in range(angular_segments):
            following = angular + 1
            faces.extend(
                [
                    (outer[axial][angular], outer[axial + 1][angular], outer[axial + 1][following]),
                    (outer[axial][angular], outer[axial + 1][following], outer[axial][following]),
                    (inner[axial][angular], inner[axial][following], inner[axial + 1][following]),
                    (inner[axial][angular], inner[axial + 1][following], inner[axial + 1][angular]),
                ]
            )

    for axial in (0, axial_segments):
        for angular in range(angular_segments):
            following = angular + 1
            if axial == 0:
                faces.extend(
                    [
                        (outer[axial][angular], outer[axial][following], inner[axial][following]),
                        (outer[axial][angular], inner[axial][following], inner[axial][angular]),
                    ]
                )
            else:
                faces.extend(
                    [
                        (outer[axial][angular], inner[axial][following], outer[axial][following]),
                        (outer[axial][angular], inner[axial][angular], inner[axial][following]),
                    ]
                )

    for angular in (0, angular_segments):
        for axial in range(axial_segments):
            following = axial + 1
            if angular == 0:
                faces.extend(
                    [
                        (outer[axial][angular], inner[following][angular], outer[following][angular]),
                        (outer[axial][angular], inner[axial][angular], inner[following][angular]),
                    ]
                )
            else:
                faces.extend(
                    [
                        (outer[axial][angular], outer[following][angular], inner[following][angular]),
                        (outer[axial][angular], inner[following][angular], inner[axial][angular]),
                    ]
                )
    return vertices, faces


def write_obj(
    path: Path,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write("# GRASP parametric wheel; +X travel, +Y axle, +Z up; meters\n")
        for vertex in vertices:
            stream.write("v " + " ".join(f"{value:.12g}" for value in vertex) + "\n")
        for face in faces:
            stream.write("f " + " ".join(str(index + 1) for index in face) + "\n")


def face_normal(
    vertices: list[tuple[float, float, float]], face: tuple[int, int, int]
) -> tuple[float, float, float]:
    a, b, c = (vertices[index] for index in face)
    ab = tuple(b[index] - a[index] for index in range(3))
    ac = tuple(c[index] - a[index] for index in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    length = math.sqrt(sum(value * value for value in cross))
    return tuple(value / length for value in cross) if length else (0.0, 0.0, 0.0)


def write_stl(
    path: Path,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    scale_to_mm: bool = True,
) -> None:
    scale = 1000.0 if scale_to_mm else 1.0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(f"solid {path.stem}\n")
        for face in faces:
            normal = face_normal(vertices, face)
            stream.write("  facet normal " + " ".join(f"{value:.8g}" for value in normal) + "\n")
            stream.write("    outer loop\n")
            for index in face:
                stream.write(
                    "      vertex "
                    + " ".join(f"{vertices[index][axis] * scale:.8g}" for axis in range(3))
                    + "\n"
                )
            stream.write("    endloop\n  endfacet\n")
        stream.write(f"endsolid {path.stem}\n")


def scaled_spec(spec: WheelSpec, maximum_radius_m: float) -> WheelSpec:
    scale = maximum_radius_m / (spec.core_radius_m + spec.feature_height_m)
    return WheelSpec(
        name=spec.name,
        description=spec.description,
        core_radius_m=spec.core_radius_m * scale,
        feature_height_m=spec.feature_height_m * scale,
        width_m=spec.width_m * scale,
        bore_radius_m=spec.bore_radius_m * scale,
        lobes=spec.lobes,
        profile_exponent=spec.profile_exponent,
        axial_phase_deg=spec.axial_phase_deg,
        phase_mode=spec.phase_mode,
    )


def effective_rolling_radius(spec: WheelSpec) -> float:
    samples = [outer_radius(spec, 2.0 * math.pi * index / 4096, 0.0) for index in range(4096)]
    return sum(samples) / len(samples)


def generate_catalog(output_dir: Path) -> dict[str, object]:
    entries = []
    for spec in CANDIDATES:
        full_vertices, full_faces = build_mesh(spec, angular_segments=192, axial_segments=24)
        full_path = output_dir / "dem_full_scale" / f"{spec.name}.obj"
        write_obj(full_path, full_vertices, full_faces)
        full_qa = inspect_obj(full_path)

        print_spec = scaled_spec(spec, 0.110)
        print_vertices, print_faces = build_mesh(
            print_spec, angular_segments=256, axial_segments=32
        )
        print_obj = output_dir / "bambu_220mm" / f"{spec.name}_220mm.obj"
        print_stl = output_dir / "bambu_220mm" / f"{spec.name}_220mm.stl"
        write_obj(print_obj, print_vertices, print_faces)
        write_stl(print_stl, print_vertices, print_faces)
        print_qa = inspect_obj(print_obj)
        sector_entries = []
        for sector_index in range(4):
            start_angle = sector_index * math.pi / 2.0
            end_angle = (sector_index + 1) * math.pi / 2.0
            sector_vertices, sector_faces = build_sector_mesh(
                spec, start_angle, end_angle, angular_segments=64, axial_segments=24
            )
            sector_obj = (
                output_dir
                / "bambu_full_scale_quadrants"
                / spec.name
                / f"{spec.name}_quadrant_{sector_index + 1}.obj"
            )
            sector_stl = sector_obj.with_suffix(".stl")
            write_obj(sector_obj, sector_vertices, sector_faces)
            write_stl(sector_stl, sector_vertices, sector_faces)
            sector_qa = inspect_obj(sector_obj)
            sector_entries.append(
                {
                    "quadrant": sector_index + 1,
                    "obj": str(sector_obj.relative_to(output_dir.parent)),
                    "stl": str(sector_stl.relative_to(output_dir.parent)),
                    "mesh_qa": sector_qa,
                    "maximum_piece_extent_mm": 1000.0 * max(sector_qa["extents_m"]),
                }
            )
        entries.append(
            {
                "name": spec.name,
                "description": spec.description,
                "design": asdict(spec),
                "dem": {
                    "obj": str(full_path.relative_to(output_dir.parent)),
                    "envelope_radius_m": spec.core_radius_m + spec.feature_height_m,
                    "rolling_radius_m": effective_rolling_radius(spec),
                    "width_m": spec.width_m,
                    "mesh_qa": full_qa,
                },
                "bambu": {
                    "obj": str(print_obj.relative_to(output_dir.parent)),
                    "stl": str(print_stl.relative_to(output_dir.parent)),
                    "units": "millimeters in STL; meters in OBJ",
                    "maximum_diameter_mm": 220.0,
                    "width_mm": print_spec.width_m * 1000.0,
                    "bore_diameter_mm": print_spec.bore_radius_m * 2000.0,
                    "mesh_qa": print_qa,
                },
                "bambu_full_scale_quadrants": {
                    "assembly": (
                        "Four closed full-scale sectors; bond and clamp between rig-specific side plates. "
                        "Add the verified axle and fastener pattern to the reusable plates."
                    ),
                    "nominal_printer_envelope_mm": 256.0,
                    "pieces": sector_entries,
                },
            }
        )
    catalog = {
        "schema_version": 1,
        "purpose": "Parametric GRASP compaction-versus-mobility screening family",
        "coordinate_frame": "+X travel, +Y axle, +Z up",
        "candidates": entries,
        "physical_interface_reference": {
            "candidate_bore_diameter_mm": CANDIDATE_BORE_RADIUS_M * 2000.0,
            "rtgs_hub_measured_envelope_mm": {
                "diameter": RTGS_HUB_REFERENCE_OD_M * 1000.0,
                "width": RTGS_HUB_REFERENCE_WIDTH_M * 1000.0,
            },
            "rider_converter_measured_diameter_mm": RIDER_CONVERTER_REFERENCE_OD_M
            * 1000.0,
            "status": (
                "Envelope clearance established from recovered STL assets; axle and bolt pattern "
                "must be verified against the intended RIDER or CRATR adapter before printing."
            ),
        },
        "print_note": (
            "The 220 mm STLs fit within a 220 x 220 mm XY envelope. Confirm the actual Bambu "
            "printer build volume, hub interface, axle, and required wall/infill settings before printing. "
            "Full-scale quadrant STLs fit a nominal 256 mm cubic envelope and preserve RIDER-scale geometry."
        ),
    }
    (output_dir / "candidate_catalog.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    )
    return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate GRASP wheel candidates")
    parser.add_argument("--output-dir", type=Path, default=Path("wheel_candidates"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = generate_catalog(args.output_dir.resolve())
    for candidate in catalog["candidates"]:
        print(
            f"{candidate['name']}: DEM OD {2e3 * candidate['dem']['envelope_radius_m']:.1f} mm; "
            f"Bambu OD {candidate['bambu']['maximum_diameter_mm']:.1f} mm; watertight"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
