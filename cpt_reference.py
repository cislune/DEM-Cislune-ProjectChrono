#!/usr/bin/env python3
"""Extract CPT profiles from the UCF Alabama workbook without Excel dependencies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import xml.etree.ElementTree as ET
import zipfile


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def column_index(cell_reference: str) -> int:
    match = re.match(r"([A-Z]+)", cell_reference.upper())
    if not match:
        raise ValueError(f"Invalid cell reference: {cell_reference}")
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root.findall(f"{{{SHEET_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{SHEET_NS}}}t")))
    return values


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    result = {}
    for sheet in workbook.findall(f".//{{{SHEET_NS}}}sheet"):
        relationship_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = PurePosixPath("xl") / targets[relationship_id]
        result[sheet.attrib["name"]] = str(target)
    return result


def _sheet_cells(
    archive: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]
) -> dict[tuple[int, int], object]:
    root = ET.fromstring(archive.read(sheet_path))
    cells: dict[tuple[int, int], object] = {}
    for cell in root.findall(f".//{{{SHEET_NS}}}c"):
        reference = cell.attrib["r"]
        row_match = re.search(r"(\d+)$", reference)
        if not row_match:
            continue
        row = int(row_match.group(1)) - 1
        column = column_index(reference)
        value_node = cell.find(f"{{{SHEET_NS}}}v")
        if value_node is None or value_node.text is None:
            continue
        raw = value_node.text
        if cell.attrib.get("t") == "s":
            value: object = shared_strings[int(raw)]
        elif cell.attrib.get("t") == "b":
            value = raw == "1"
        else:
            try:
                value = float(raw)
            except ValueError:
                value = raw
        cells[(row, column)] = value
    return cells


def read_xlsx(path: Path) -> dict[str, dict[tuple[int, int], object]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        return {
            name: _sheet_cells(archive, target, shared_strings)
            for name, target in _sheet_paths(archive).items()
        }


def linear_fit(points: list[tuple[float, float]]) -> dict[str, float]:
    if len(points) < 2:
        raise ValueError("At least two points are required for a linear fit")
    x_mean = statistics.fmean(point[0] for point in points)
    y_mean = statistics.fmean(point[1] for point in points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    intercept = y_mean - slope * x_mean
    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    total = sum((y - y_mean) ** 2 for _, y in points)
    return {
        "slope_kpa_per_mm": slope,
        "intercept_kpa": intercept,
        "r_squared": 1.0 - residual / total if total else 1.0,
    }


def interpolate(points: list[tuple[float, float]], target_x: float) -> float:
    ordered = sorted(points)
    for x, value in ordered:
        if math.isclose(x, target_x, rel_tol=0.0, abs_tol=1e-9):
            return value
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= target_x <= x1:
            fraction = (target_x - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)
    raise ValueError(f"Target {target_x} is outside profile range")


def extract_sheet_profile(
    cells: dict[tuple[int, int], object], max_depth_mm: float = 400.0
) -> dict[str, object]:
    profiles: list[list[tuple[float, float]]] = [[] for _ in range(4)]
    rows: list[dict[str, object]] = []
    row_numbers = sorted({row for row, _ in cells})
    for row in row_numbers:
        depth = cells.get((row, 0))
        values = [cells.get((row, column)) for column in range(1, 5)]
        if not isinstance(depth, (int, float)) or not 0 < float(depth) <= max_depth_mm:
            continue
        if not all(isinstance(value, (int, float)) for value in values):
            continue
        depth_value = float(depth)
        numeric_values = [float(value) for value in values]
        for profile, value in zip(profiles, numeric_values):
            profile.append((depth_value, value))
        rows.append(
            {
                "depth_mm": depth_value,
                "insertion_kpa": numeric_values,
                "mean_kpa": statistics.fmean(numeric_values),
                "std_kpa": statistics.stdev(numeric_values),
            }
        )

    if not rows:
        raise ValueError("No four-insertion CPT profile was found")
    shallow_profiles = [
        [(depth, value) for depth, value in profile if depth <= 100.0]
        for profile in profiles
    ]
    mean_profile = [(row["depth_mm"], row["mean_kpa"]) for row in rows]
    metadata = {}
    for row in row_numbers:
        label = cells.get((row, 0))
        if label == "Bulk Density (g/cm3)":
            values = [float(cells[(row, column)]) for column in range(1, 5)]
            metadata["bulk_density_g_cm3"] = {
                "insertions": values,
                "mean": statistics.fmean(values),
                "std": statistics.stdev(values),
            }
        elif label == "Relative Density (%)":
            values = [float(cells[(row, column)]) for column in range(1, 5)]
            metadata["relative_density_percent"] = {
                "insertions": values,
                "mean": statistics.fmean(values),
                "std": statistics.stdev(values),
            }

    return {
        "rows": rows,
        "metadata": metadata,
        "insertions": [
            {
                "insertion": index + 1,
                "q_100mm_kpa": interpolate(profile, 100.0),
                "fit_10_to_100mm": linear_fit(shallow),
            }
            for index, (profile, shallow) in enumerate(zip(profiles, shallow_profiles))
        ],
        "aggregate": {
            "q_100mm_mean_kpa": statistics.fmean(
                interpolate(profile, 100.0) for profile in profiles
            ),
            "q_100mm_std_kpa": statistics.stdev(
                interpolate(profile, 100.0) for profile in profiles
            ),
            "mean_profile_fit_10_to_100mm": linear_fit(
                [(depth, value) for depth, value in mean_profile if depth <= 100.0]
            ),
        },
    }


def extract_reference(path: Path) -> dict[str, object]:
    workbook = read_xlsx(path)
    required = ("Alabama In-Track", "Alabama Out-Track")
    missing = [name for name in required if name not in workbook]
    if missing:
        raise ValueError(f"Missing expected worksheet(s): {', '.join(missing)}")
    states = {
        "in_track": extract_sheet_profile(workbook["Alabama In-Track"]),
        "out_track": extract_sheet_profile(workbook["Alabama Out-Track"]),
    }
    in_strength = states["in_track"]["aggregate"]["q_100mm_mean_kpa"]
    out_strength = states["out_track"]["aggregate"]["q_100mm_mean_kpa"]
    return {
        "schema_version": 1,
        "source": {
            "filename": path.name,
            "sha256": sha256_file(path),
            "worksheets": list(workbook),
        },
        "test": {
            "wheel": "Alabama wheel scaled and printed by Cislune",
            "facility": "UCF RIDER",
            "wheel_traffic_date": "2026-08-04",
            "cpt_date": "2026-08-13",
            "cone_base_area_m2": 1.3e-4,
            "cone_base_diameter_m": 0.01286,
            "cone_included_angle_deg": 30.0,
            "interpretation": (
                "Post-traffic spatial contrast. In-track and out-track insertions are not a "
                "controlled before-and-after pair because the lane was not reset."
            ),
        },
        "states": states,
        "derived": {
            "in_to_out_q100_ratio": in_strength / out_strength,
            "in_to_out_bulk_density_ratio": (
                states["in_track"]["metadata"]["bulk_density_g_cm3"]["mean"]
                / states["out_track"]["metadata"]["bulk_density_g_cm3"]["mean"]
            ),
            "recommended_baseline_target": "out_track",
            "recommended_post_traffic_validation_target": "in_track",
        },
    }


def write_tidy_csv(reference: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["state", "depth_mm", "insertion_1_kpa", "insertion_2_kpa", "insertion_3_kpa", "insertion_4_kpa", "mean_kpa", "std_kpa"]
        )
        for state, profile in reference["states"].items():
            for row in profile["rows"]:
                writer.writerow(
                    [state, row["depth_mm"], *row["insertion_kpa"], row["mean_kpa"], row["std_kpa"]]
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Alabama UCF CPT profiles from XLSX")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--csv", type=Path, required=True, dest="csv_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reference = extract_reference(args.workbook.resolve())
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n")
    write_tidy_csv(reference, args.csv_path)
    print(f"Wrote {args.json_path}")
    print(f"Wrote {args.csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
