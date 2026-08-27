import csv
import tempfile
import unittest
from pathlib import Path

import analyze_dem_output as analyzer


def write_xyz(path: Path, points: list[tuple[float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["X", "Y", "Z", "r"])
        for point in points:
            writer.writerow([*point, 0.01])


class AnalyzeDemOutputTests(unittest.TestCase):
    def test_rejects_stale_settled_particle_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_xyz(root / "terrain motion" / "terrain_0000.csv", [(0, 0, 0), (0.1, 0, 0)])
            write_xyz(root / "settled data" / "settled.csv", [(0, 0, 0)])
            result = analyzer.analyze(root)
        self.assertEqual(result["status"], "REJECT")
        self.assertTrue(any("stale or incoherent" in item for item in result["failures"]))

    def test_passes_coherent_minimal_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            points = [(0, 0, 0), (0.1, 0, 0)]
            write_xyz(root / "terrain motion" / "terrain_0000.csv", points)
            write_xyz(root / "settled data" / "settled.csv", points)
            result = analyzer.analyze(root)
        self.assertEqual(result["status"], "PASS_SOFTWARE_INTEGRITY")


if __name__ == "__main__":
    unittest.main()
