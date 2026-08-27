import csv
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import rider_reference


FIELDS = [
    "timeElapsed",
    "totalDist",
    "actualRPS",
    "wheelDiameter",
    "wheelCmPerSec",
    "desiredCmPerSec",
    "torqueNm",
    "lapCounter",
    "appliedLoad",
    "desiredMass",
]


def lap_text() -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(
        [
            dict(zip(FIELDS, row))
            for row in [
                (0.0, 0.0, 0.0, 38.0, 0.0, 10.0, 0.0, 1, 10.0, 10.0),
                (0.1, 1.0, 0.08, 38.0, 10.0, 10.0, 3.0, 1, 9.0, 10.0),
                (0.1, 1.0, 0.08, 38.0, 10.0, 10.0, 3.0, 1, 11.0, 10.0),
                (0.2, 2.0, 0.08, 38.0, 10.0, 10.0, 4.0, 1, 10.0, 10.0),
            ]
        ]
    )
    return stream.getvalue()


class RiderReferenceTests(unittest.TestCase):
    def test_build_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "rider.zip"
            with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("run/1.TXT", lap_text())
            result = rider_reference.build_reference(archive_path)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(len(result["laps"]), 1)
        lap = result["laps"][0]
        self.assertEqual(lap["file_lap"], 1)
        self.assertEqual(lap["unique_timestamps"], 3)
        self.assertAlmostEqual(lap["distance_delta_m"], 0.02)
        self.assertAlmostEqual(lap["wheel_diameter_m"], 0.38)
        self.assertEqual(lap["active_motion_rows"], 3)
        self.assertEqual(lap["derived_interval_count"], 1)
        self.assertAlmostEqual(lap["derived_slip"]["median"], 0.0)
        self.assertEqual(result["campaign_summary"]["lap_count"], 1)
        self.assertEqual(result["campaign_summary"]["derived_interval_count"], 1)

    def test_missing_required_column_is_rejected(self):
        stream = io.StringIO("timeElapsed,totalDist\n0,0\n")
        with self.assertRaises(rider_reference.RiderDataError):
            rider_reference.read_lap(stream, "bad.txt")


if __name__ == "__main__":
    unittest.main()
