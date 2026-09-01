import unittest
from pathlib import Path
import json
import tempfile

import analyze_wheel_performance as analysis


class AnalyzeWheelPerformanceTests(unittest.TestCase):
    def test_lane_strain_for_uniform_compression(self):
        initial = [(0.1 * i, 0.0, 0.01 * i) for i in range(20)]
        final = [(x, y, z * 0.9) for x, y, z in initial]
        metrics = analysis.lane_metrics(initial, final, 0.0, 2.0, 0.1)
        self.assertAlmostEqual(metrics["column_strain_proxy"], 0.1)
        self.assertGreater(metrics["p95_surface_settlement_m"], 0.0)

    def test_lane_threshold_is_explicit_for_coarse_checkout(self):
        initial = [(0.01 * i, 0.0, 0.01 * i) for i in range(8)]
        final = [(x, y, z * 0.9) for x, y, z in initial]
        with self.assertRaisesRegex(ValueError, "found 8, require 10"):
            analysis.lane_metrics(initial, final, 0.0, 0.1, 0.1)
        metrics = analysis.lane_metrics(initial, final, 0.0, 0.1, 0.1, 5)
        self.assertEqual(metrics["particles"], 8)

    def test_quantile(self):
        self.assertEqual(analysis.quantile([0.0, 10.0], 0.5), 5.0)

    def test_density_gate_rejects_mismatched_imported_bed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            terrain = Path(temp_dir) / "terrain"
            terrain.mkdir()
            (terrain / "terrain_preparation.json").write_text(
                json.dumps(
                    {
                        "target_bulk_density_kg_m3": 1700.0,
                        "post_release_bulk_density_kg_m3": 1500.0,
                    }
                )
            )
            gate = analysis.density_gate(Path(temp_dir))
        self.assertEqual(gate["status"], "REJECT_DENSITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
