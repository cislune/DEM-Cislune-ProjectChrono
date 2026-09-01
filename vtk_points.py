"""Small, dependency-free readers for legacy ASCII VTK point data."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_ascii_vtk_point_centroid(path: Path) -> np.ndarray:
    """Return the centroid of the POINTS block in a legacy ASCII VTK file."""
    with path.open("r", encoding="utf-8", errors="strict") as stream:
        header = [stream.readline().strip() for _ in range(3)]
        if len(header) < 3 or header[2].upper() != "ASCII":
            raise ValueError(f"Expected legacy ASCII VTK data: {path}")

        point_count = None
        for line in stream:
            fields = line.split()
            if fields and fields[0].upper() == "POINTS":
                if len(fields) < 3:
                    raise ValueError(f"Malformed POINTS header: {path}")
                point_count = int(fields[1])
                break

        if point_count is None or point_count <= 0:
            raise ValueError(f"No nonempty POINTS block found: {path}")

        sums = np.zeros(3, dtype=float)
        value_count = 0
        required_values = 3 * point_count
        for line in stream:
            for token in line.split():
                if value_count >= required_values:
                    break
                sums[value_count % 3] += float(token)
                value_count += 1
            if value_count >= required_values:
                break

    if value_count != required_values:
        raise ValueError(
            f"POINTS block in {path} declares {point_count} points but contains "
            f"only {value_count // 3} complete points"
        )
    return sums / point_count
