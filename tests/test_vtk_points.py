from pathlib import Path

import numpy as np
import pytest

from vtk_points import read_ascii_vtk_point_centroid


def test_reads_ascii_vtk_point_centroid(tmp_path: Path):
    path = tmp_path / "wheel.vtk"
    path.write_text(
        "# vtk DataFile Version 2.0\n"
        "wheel\n"
        "ASCII\n"
        "DATASET UNSTRUCTURED_GRID\n"
        "POINTS 3 float\n"
        "0 0 0  3 6 9\n"
        "6 3 0\n"
        "CELLS 0 0\n"
    )

    np.testing.assert_allclose(read_ascii_vtk_point_centroid(path), [3.0, 3.0, 3.0])


def test_rejects_truncated_points_block(tmp_path: Path):
    path = tmp_path / "truncated.vtk"
    path.write_text(
        "# vtk DataFile Version 2.0\nwheel\nASCII\n"
        "DATASET UNSTRUCTURED_GRID\nPOINTS 2 float\n0 0 0\n"
    )

    with pytest.raises(ValueError, match="only 1 complete points"):
        read_ascii_vtk_point_centroid(path)
