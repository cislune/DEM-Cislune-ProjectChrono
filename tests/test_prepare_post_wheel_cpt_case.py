import csv
from pathlib import Path
import tempfile
import unittest

from prepare_post_wheel_cpt_case import crop_state


class PreparePostWheelCptCaseTests(unittest.TestCase):
    def test_crop_recenters_and_shifts_floor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["X", "Y", "Z", "clump_type"])
                writer.writeheader()
                for i in range(8):
                    for j in range(8):
                        writer.writerow(
                            {"X": 1.0 + (i - 3.5) * 0.004, "Y": 2.0 + (j - 3.5) * 0.004, "Z": 0.1, "clump_type": "t0"}
                        )
            output = root / "crop.csv"
            count, rows = crop_state(source, output, 1.0, 2.0, 0.06, 0.06, 0.002, -0.015)
            self.assertEqual(count, 64)
            self.assertAlmostEqual(float(rows[0]["Z"]), 0.085)
            self.assertLess(max(abs(float(row["X"])) for row in rows), 0.02)


if __name__ == "__main__":
    unittest.main()
