#!/usr/bin/env python3
"""Infer wheel rigid motion from DEME mesh frames and verify rolling sign/slip."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def read_vtk_points(path: Path) -> np.ndarray:
    points = []
    with path.open(errors="strict") as stream:
        iterator = iter(stream)
        expected = None
        for line in iterator:
            if line.startswith("POINTS "):
                expected = int(line.split()[1])
                break
        if expected is None:
            raise ValueError(f"{path} has no POINTS section")
        values = []
        for line in iterator:
            values.extend(float(value) for value in line.split())
            while len(values) >= 3 and len(points) < expected:
                points.append(values[:3])
                values = values[3:]
            if len(points) == expected:
                break
    if len(points) != expected:
        raise ValueError(f"{path} declared {expected} points but contained {len(points)}")
    return np.asarray(points, dtype=float)


def infer_rigid_motion(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    if before.shape != after.shape or before.ndim != 2 or before.shape[1] != 3:
        raise ValueError("Mesh frames must contain matching Nx3 point arrays")
    before_center = before.mean(axis=0)
    after_center = after.mean(axis=0)
    a = before - before_center
    b = after - after_center
    u, _, vt = np.linalg.svd(a.T @ b)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    translation = after_center - rotation @ before_center
    residual = float(np.sqrt(np.mean(np.sum(((rotation @ before.T).T + translation - after) ** 2, axis=1))))
    return rotation, translation, residual


def frame_number(path: Path) -> int:
    return int(path.stem.rsplit("_", 1)[-1])


def verify(frame_paths: list[Path], manifest: dict) -> dict:
    if len(frame_paths) < 2:
        raise ValueError("At least two wheel VTK frames are required for the spin gate")
    first, second = sorted(frame_paths, key=frame_number)[:2]
    frame_delta = frame_number(second) - frame_number(first)
    frame_time = float(manifest["output"]["wheel_frame_time_s"])
    elapsed = frame_delta * frame_time
    if elapsed <= 0:
        raise ValueError("Wheel frame timestamps are not increasing")
    rotation, translation, residual = infer_rigid_motion(
        read_vtk_points(first), read_vtk_points(second)
    )
    angle_y = math.atan2(float(rotation[0, 2]), float(rotation[0, 0]))
    omega_y = angle_y / elapsed
    velocity_x = float(translation[0]) / elapsed
    rolling_radius = float(manifest["wheel"]["rolling_radius_m"])
    commanded_slip = float(manifest["test"]["slip_ratios"][0])
    expected_omega = float(manifest["test"]["linear_speed_m_s"]) / (
        (1.0 - commanded_slip) * rolling_radius
    )
    inferred_slip = 1.0 - velocity_x / (omega_y * rolling_radius) if omega_y else None
    sign_pass = velocity_x * omega_y > 0.0
    speed_ratio = omega_y / expected_omega if expected_omega else None
    slip_error = inferred_slip - commanded_slip if inferred_slip is not None else None
    passed = bool(
        sign_pass
        and speed_ratio is not None
        and 0.98 <= speed_ratio <= 1.02
        and slip_error is not None
        and abs(slip_error) <= 0.02
        and residual <= 1e-5
    )
    return {
        "status": "PASS_REFERENCE_SPIN" if passed else "REJECT_REFERENCE_SPIN",
        "first_frame": str(first),
        "second_frame": str(second),
        "elapsed_s": elapsed,
        "translation_x_m": float(translation[0]),
        "linear_velocity_x_m_s": velocity_x,
        "rotation_about_y_rad": angle_y,
        "angular_velocity_y_rad_s": omega_y,
        "expected_angular_velocity_rad_s": expected_omega,
        "angular_speed_ratio": speed_ratio,
        "commanded_slip": commanded_slip,
        "inferred_kinematic_slip": inferred_slip,
        "slip_error": slip_error,
        "forward_spin_sign_pass": sign_pass,
        "rigid_fit_rms_m": residual,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_dir = args.case_dir.resolve()
    manifest = json.loads((case_dir / "frozen_case.json").read_text())
    frames = list((case_dir / "wheel").glob("slip_*/pass_*/Trial 1/Slip */wheel motion/*.vtk"))
    result = verify(frames, manifest)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output = args.output or case_dir / "reference_spin_gate.json"
    output.write_text(rendered)
    print(rendered, end="")
    return 0 if result["status"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
