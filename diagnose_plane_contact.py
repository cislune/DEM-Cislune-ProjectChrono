#!/usr/bin/env python3
"""Minimal PyDEME sphere-plane regression check for the pinned container."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import DEME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--boundary", choices=("explicit", "box", "both"), default="explicit")
    parser.add_argument("--radius-m", type=float, default=0.02)
    parser.add_argument("--duration-s", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    radius = args.radius_m
    density = 2500.0
    mass = (4.0 / 3.0) * math.pi * radius**3 * density

    solver = DEME.DEMSolver()
    solver.SetVerbosity("INFO")
    solver.SetOutputFormat("CSV")
    solver.SetOutputContent(["XYZ", "QUAT", "VEL", "ANG_VEL"])
    solver.SetContactOutputContent(["OWNER", "FORCE", "POINT"])
    solver.SetMaxVelocity(30.0)
    solver.SetErrorOutVelocity(30.0)
    solver.SetInitTimeStep(5e-6)
    solver.SetGravitationalAcceleration([0.0, 0.0, -9.81])
    material = solver.LoadMaterial(
        {"E": 100000.0, "nu": 0.24, "CoR": 0.3, "mu": 0.3, "Crr": 0.1, "Cohesion": 0.0}
    )
    solver.InstructBoxDomainDimension([-0.2, 0.2], [-0.2, 0.2], [-0.1, 0.3])
    if args.boundary in {"box", "both"}:
        solver.InstructBoxDomainBoundingBC("top_open", material)
    if args.boundary in {"explicit", "both"}:
        solver.AddBCPlane([0.0, 0.0, -0.1], [0.0, 0.0, 1.0], material)

    template = solver.LoadSphereType(mass, radius, material)
    batch = solver.AddClumps(template, [[0.0, 0.0, -0.06]])
    batch.SetFamilies([0])
    batch.SetOriQ([0.0, 0.0, 0.0, 1.0])
    solver.Initialize()

    frame_time = 1e-3
    frame = 0
    time_s = 0.0
    while time_s < args.duration_s:
        if frame % 10 == 0:
            solver.WriteSphereFile(str(args.output / f"sphere_{frame:04d}.csv"))
            solver.WriteContactFile(str(args.output / f"contact_{frame:04d}.csv"))
        solver.DoDynamics(frame_time)
        time_s += frame_time
        frame += 1
    solver.WriteClumpFile(str(args.output / "final.csv"))


if __name__ == "__main__":
    main()
