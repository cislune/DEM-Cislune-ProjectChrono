from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import cpt_case_runner as runner
from dem_case_runner import inspect_obj


class CptCaseRunnerTests(unittest.TestCase):
    def test_generated_probe_is_watertight(self):
        probe = {
            "base_diameter_m": 0.01286,
            "included_angle_deg": 30.0,
            "shaft_diameter_m": 0.0075,
            "shaft_length_m": 0.15,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "probe.obj"
            runner.generate_probe_obj(path, probe)
            report = inspect_obj(path)
        self.assertTrue(report["watertight_two_manifold"])
        self.assertEqual(report["non_triangular_faces"], 0)
        self.assertAlmostEqual(report["extents_m"][0], 0.01286, places=6)

    def test_smoke_preflight(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, report = runner.preflight_case(
                root / "cases" / "cpt_alabama_out_track_smoke.json",
                root,
                Path(temp_dir),
            )
        self.assertEqual(report["status"], "PASS")
        self.assertLess(report["estimated_initial_particle_count"], 1000)
        self.assertIsNotNone(report["physical_reference_sha256"])

    def test_binned_profile_uses_median(self):
        profile = runner.binned_profile(
            [(0.010, 100.0), (0.011, 10000.0), (0.009, 200.0)], 0.005
        )
        self.assertEqual(profile, [(0.01, 200.0, 3)])

    def test_imported_initial_state_is_staged_without_regeneration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text("X,Y,Z,clump_type\n0,0,0,t0\n")
            paths = {"terrain": root / "terrain"}
            config = SimpleNamespace(
                TERRAIN_INITIAL_STATE_CSV_st=str(source),
                TERRAIN_IMPORTED_PREPARATION_st={
                    "source_preparation": "/source/terrain_preparation.json",
                    "source_preparation_sha256": "abc123",
                    "target_bulk_density_kg_m3": 1703.2,
                    "post_release_bulk_density_kg_m3": 1654.2,
                },
            )
            runner.run_terrain(root, config, paths, overwrite=True)
            target = runner.settled_terrain_path(paths["terrain"])
            self.assertEqual(target.read_text(), source.read_text())
            preparation = runner.json.loads(
                (paths["terrain"] / "terrain_preparation.json").read_text()
            )
            self.assertEqual(preparation["target_bulk_density_kg_m3"], 1703.2)
            self.assertEqual(preparation["post_release_bulk_density_kg_m3"], 1654.2)


if __name__ == "__main__":
    unittest.main()
