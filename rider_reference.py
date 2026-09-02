#!/usr/bin/env python3
"""Build a traceable physical-reference summary from a UCF RIDER ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable
from zipfile import ZipFile


REQUIRED_COLUMNS = {
    "timeElapsed",
    "totalDist",
    "actualRPS",
    "wheelDiameter",
    "wheelCmPerSec",
    "desiredCmPerSec",
    "torqueNm",
    "directionStatus",
    "lapCounter",
    "appliedLoad",
    "desiredMass",
}


class RiderDataError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_float(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RiderDataError(f"Invalid {field} value: {value!r}") from exc
    if not math.isfinite(result):
        raise RiderDataError(f"Non-finite {field} value: {value!r}")
    return result


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
        "p05": quantile(finite, 0.05),
        "median": statistics.median(finite) if finite else None,
        "mean": statistics.fmean(finite) if finite else None,
        "p95": quantile(finite, 0.95),
        "max": max(finite) if finite else None,
    }


def read_lap(stream: io.TextIOBase, source_name: str) -> list[dict[str, float]]:
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        raise RiderDataError(f"{source_name} has no header")
    missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
    if missing:
        raise RiderDataError(f"{source_name} is missing columns: {', '.join(missing)}")

    rows: list[dict[str, float]] = []
    for line_number, raw in enumerate(reader, 2):
        if not raw or not any((value or "").strip() for value in raw.values()):
            continue
        row = {
            field: finite_float(raw[field], field)
            for field in REQUIRED_COLUMNS
        }
        rows.append(row)
    if not rows:
        raise RiderDataError(f"{source_name} has no data rows")
    return rows


def active_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    active = []
    for row in rows:
        desired = abs(row["desiredCmPerSec"])
        threshold = max(1.0, 0.10 * desired)
        if abs(row["wheelCmPerSec"]) >= threshold:
            active.append(row)
    return active


def unique_time_samples(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    """Collapse repeated timestamps using the last distance and median wheel speed."""
    grouped: dict[float, list[dict[str, float]]] = {}
    for row in rows:
        grouped.setdefault(row["timeElapsed"], []).append(row)
    result = []
    for timestamp in sorted(grouped):
        group = grouped[timestamp]
        result.append(
            {
                "time_s": timestamp,
                "distance_cm": group[-1]["totalDist"],
                "wheel_speed_cm_s": statistics.median(
                    abs(item["wheelCmPerSec"]) for item in group
                ),
                "load_kg_reported": statistics.median(
                    item["appliedLoad"] for item in group
                ),
                "abs_torque_nm": statistics.median(
                    abs(item["torqueNm"]) for item in group
                ),
            }
        )
    return result


def kinematic_intervals(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    samples = unique_time_samples(rows)
    intervals = []
    for previous, current in zip(samples, samples[1:]):
        dt = current["time_s"] - previous["time_s"]
        dx = current["distance_cm"] - previous["distance_cm"]
        wheel_speed = 0.5 * (
            previous["wheel_speed_cm_s"] + current["wheel_speed_cm_s"]
        )
        if not 0.05 <= dt <= 0.50:
            continue
        if previous["wheel_speed_cm_s"] < 1.0 or current["wheel_speed_cm_s"] < 1.0:
            continue
        carriage_speed = dx / dt
        if wheel_speed < 1.0 or not 0.0 <= carriage_speed <= 30.0:
            continue
        slip = 1.0 - carriage_speed / wheel_speed
        if not -1.0 <= slip <= 1.0:
            continue
        intervals.append(
            {
                "time_s": current["time_s"],
                "dt_s": dt,
                "carriage_speed_cm_s": carriage_speed,
                "wheel_speed_cm_s": wheel_speed,
                "slip": slip,
                "load_kg_reported": current["load_kg_reported"],
                "abs_torque_nm": current["abs_torque_nm"],
            }
        )
    return intervals


def summarize_lap(source_name: str, rows: list[dict[str, float]]) -> dict[str, Any]:
    active = active_rows(rows)
    intervals = kinematic_intervals(rows)
    desired_speed = statistics.median(row["desiredCmPerSec"] for row in rows)
    desired_mass = statistics.median(row["desiredMass"] for row in rows)
    wheel_diameter = statistics.median(row["wheelDiameter"] for row in rows)
    speed_tolerance = 0.20 * abs(desired_speed)
    load_tolerance = 3.0
    motion_threshold = max(1.0, 0.10 * abs(desired_speed))
    stationary_loaded = [
        row
        for row in rows
        if abs(row["wheelCmPerSec"]) < motion_threshold
        and abs(row["appliedLoad"] - desired_mass) <= load_tolerance
    ]
    if not stationary_loaded:
        raise RiderDataError(
            f"{source_name} has no loaded stationary rows for torque baseline correction"
        )
    torque_baseline_by_direction = {
        direction: statistics.median(
            row["torqueNm"]
            for row in stationary_loaded
            if row["directionStatus"] == direction
        )
        for direction in sorted({row["directionStatus"] for row in stationary_loaded})
    }
    fallback_torque_baseline = statistics.median(
        row["torqueNm"] for row in stationary_loaded
    )

    def corrected_abs_torque(row: dict[str, float]) -> float:
        baseline = torque_baseline_by_direction.get(
            row["directionStatus"], fallback_torque_baseline
        )
        return abs(row["torqueNm"] - baseline)

    steady_controlled = [
        row
        for row in active
        if abs(abs(row["wheelCmPerSec"]) - abs(desired_speed)) <= speed_tolerance
        and abs(row["appliedLoad"] - desired_mass) <= load_tolerance
    ]

    return {
        "source_name": source_name,
        "reported_lap_counters": sorted({int(row["lapCounter"]) for row in rows}),
        "raw_rows": len(rows),
        "unique_timestamps": len({row["timeElapsed"] for row in rows}),
        "elapsed_span_s": max(row["timeElapsed"] for row in rows)
        - min(row["timeElapsed"] for row in rows),
        "distance_delta_m": (
            max(row["totalDist"] for row in rows)
            - min(row["totalDist"] for row in rows)
        )
        / 100.0,
        "wheel_diameter_m": wheel_diameter / 100.0,
        "desired_speed_m_s": desired_speed / 100.0,
        "desired_mass_kg_reported": desired_mass,
        "active_motion_rows": len(active),
        "active_load_kg_reported": describe(row["appliedLoad"] for row in active),
        "active_abs_torque_nm": describe(abs(row["torqueNm"]) for row in active),
        "stationary_loaded_rows": len(stationary_loaded),
        "stationary_loaded_torque_nm_by_direction": {
            f"{direction:g}": describe(
                row["torqueNm"]
                for row in stationary_loaded
                if row["directionStatus"] == direction
            )
            for direction in torque_baseline_by_direction
        },
        "active_tare_corrected_abs_torque_nm": describe(
            corrected_abs_torque(row) for row in active
        ),
        "steady_controlled_rows": len(steady_controlled),
        "steady_tare_corrected_abs_torque_nm": describe(
            corrected_abs_torque(row) for row in steady_controlled
        ),
        "active_wheel_speed_m_s": describe(
            abs(row["wheelCmPerSec"]) / 100.0 for row in active
        ),
        "active_speed_within_20pct_fraction": (
            sum(
                abs(abs(row["wheelCmPerSec"]) - abs(desired_speed))
                <= speed_tolerance
                for row in active
            )
            / len(active)
            if active
            else None
        ),
        "active_load_within_desired_plusminus_3kg_fraction": (
            sum(abs(row["appliedLoad"] - desired_mass) <= load_tolerance for row in active)
            / len(active)
            if active
            else None
        ),
        "derived_interval_count": len(intervals),
        "derived_carriage_speed_m_s": describe(
            row["carriage_speed_cm_s"] / 100.0 for row in intervals
        ),
        "derived_wheel_speed_m_s": describe(
            row["wheel_speed_cm_s"] / 100.0 for row in intervals
        ),
        "derived_slip": describe(row["slip"] for row in intervals),
        "interpretation": (
            "Derived carriage speed and slip use de-duplicated timestamps and reject "
            "nonpositive distance, dt outside 0.05-0.50 s, carriage speed above 0.30 m/s, "
            "wheel speed below 0.01 m/s, and slip outside [-1, 1]. Torque correction "
            "subtracts the same-lap, same-direction median torque measured while the "
            "loaded wheel was stationary. The residual still includes dynamic rig and "
            "drivetrain losses and is therefore an upper bound on wheel-soil contact torque."
        ),
    }


def campaign_summary(laps: list[dict[str, Any]]) -> dict[str, Any]:
    def range_of(path: tuple[str, ...]) -> list[float]:
        values = []
        for lap in laps:
            value: Any = lap
            for key in path:
                value = value[key]
            if value is not None:
                values.append(float(value))
        return [min(values), max(values)] if values else []

    lap_slips = [
        lap["derived_slip"]["median"]
        for lap in laps
        if lap["derived_slip"]["median"] is not None
    ]
    corrected_torque = [
        lap["active_tare_corrected_abs_torque_nm"]["median"]
        for lap in laps
        if lap["active_tare_corrected_abs_torque_nm"]["median"] is not None
    ]
    steady_corrected_torque = [
        lap["steady_tare_corrected_abs_torque_nm"]["median"]
        for lap in laps
        if lap["steady_tare_corrected_abs_torque_nm"]["median"] is not None
    ]
    return {
        "lap_count": len(laps),
        "total_distance_m": sum(lap["distance_delta_m"] for lap in laps),
        "lap_distance_range_m": range_of(("distance_delta_m",)),
        "active_load_median_range_kg_reported": range_of(
            ("active_load_kg_reported", "median")
        ),
        "active_load_mean_range_kg_reported": range_of(
            ("active_load_kg_reported", "mean")
        ),
        "active_abs_torque_median_range_nm": range_of(
            ("active_abs_torque_nm", "median")
        ),
        "active_tare_corrected_abs_torque_median_range_nm": range_of(
            ("active_tare_corrected_abs_torque_nm", "median")
        ),
        "active_tare_corrected_abs_torque_median_of_lap_medians_nm": (
            statistics.median(corrected_torque) if corrected_torque else None
        ),
        "steady_tare_corrected_abs_torque_median_range_nm": range_of(
            ("steady_tare_corrected_abs_torque_nm", "median")
        ),
        "steady_tare_corrected_abs_torque_median_of_lap_medians_nm": (
            statistics.median(steady_corrected_torque)
            if steady_corrected_torque
            else None
        ),
        "derived_slip_lap_median_range": range_of(("derived_slip", "median")),
        "derived_slip_median_of_lap_medians": (
            statistics.median(lap_slips) if lap_slips else None
        ),
        "derived_interval_count": sum(lap["derived_interval_count"] for lap in laps),
    }


def build_reference(zip_path: Path) -> dict[str, Any]:
    lap_entries: list[tuple[int, str]] = []
    with ZipFile(zip_path) as archive:
        for name in archive.namelist():
            stem = Path(name).stem
            if name.lower().endswith(".txt") and stem.isdigit():
                lap_entries.append((int(stem), name))
        lap_entries.sort()
        if not lap_entries:
            raise RiderDataError(f"No numbered lap TXT files found in {zip_path}")

        laps = []
        for expected_lap, name in lap_entries:
            with archive.open(name) as raw:
                stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                rows = read_lap(stream, name)
            lap = summarize_lap(name, rows)
            lap["file_lap"] = expected_lap
            laps.append(lap)

    return {
        "schema_version": 1,
        "source": {
            "path": str(zip_path.resolve()),
            "sha256": sha256_file(zip_path),
            "facility": "UCF RIDER",
            "test_date": "2026-08-04",
            "wheel": "Cislune Alabama wheel",
        },
        "units": {
            "timeElapsed": "s",
            "totalDist": "cm in source; converted to m in summary",
            "wheelDiameter": "cm in source; converted to m in summary",
            "wheelCmPerSec": "cm/s in source; converted to m/s in summary",
            "torqueNm": "N-m",
            "directionStatus": "dimensionless direction-state channel",
            "appliedLoad": "kg-equivalent as reported by RIDER",
            "desiredMass": "kg-equivalent as reported by RIDER",
            "derived_slip": "dimensionless, 1 - carriage_speed / wheel_surface_speed",
        },
        "conversion": {
            "kg_equivalent_to_newton": 9.80665,
            "qualification": (
                "Load conversion assumes the reported RIDER appliedLoad channel is kg-force "
                "equivalent. Preserve the reported channel and calibration record with any "
                "converted force result."
            ),
        },
        "campaign_summary": campaign_summary(laps),
        "laps": laps,
        "quality_flags": [
            "Applied-load transients substantially exceed the 10 kg desired setting in raw data.",
            "Raw torque has a large direction-dependent zero-speed offset. Use the direction-conditioned, loaded-stationary baseline-corrected metric for DEM comparison, not raw absolute torque.",
            "Baseline-corrected torque still includes dynamic drivetrain and rig losses; it is an upper bound on DEM wheel-soil contact torque until an unloaded rotating tare is available.",
            "Repeated timestamps require explicit de-duplication before velocity or slip derivation.",
            "Use synchronized time histories or bounded distributions, not only nominal load and speed, for DEM matching.",
            "The August 13 CPT campaign is a post-traffic spatial contrast because the lane was not fully reset.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("rider_zip", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reference = build_reference(args.rider_zip.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
