import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import dem_case_runner as runner


class DemCaseRunnerTests(unittest.TestCase):
    def test_alabama_case_preflight(self):
        root = Path(__file__).resolve().parents[1]
        manifest = root / "cases" / "alabama_rider_checkout.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, report = runner.preflight_case(manifest, root, Path(temp_dir))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["mesh"]["watertight_two_manifold"])
        self.assertAlmostEqual(report["measured_envelope_radius_m"], 0.204, places=6)
        self.assertAlmostEqual(report["measured_width_m"], 0.1016002, places=6)
        self.assertEqual(report["derived"]["estimated_initial_particle_count"], 10084)
        self.assertIsNotNone(report["physical_reference_sha256"])

    def test_smoke_case_preflight(self):
        root = Path(__file__).resolve().parents[1]
        manifest = root / "cases" / "alabama_rider_smoke.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, report = runner.preflight_case(manifest, root, Path(temp_dir))
        self.assertEqual(report["status"], "PASS")
        self.assertLess(report["derived"]["estimated_initial_particle_count"], 1000)
        omega = report["derived"]["angular_speed_rad_s_by_slip"]["0.0939678"]
        self.assertAlmostEqual(omega, 0.580902, places=5)

    def test_terrain_only_coupon_can_be_shorter_than_wheel_travel(self):
        root = Path(__file__).resolve().parents[1]
        manifest = (
            root
            / "cases"
            / "wheel_density_particle_scale_sweep"
            / "wheel-density-coupon-r6mm-dt3p75us-l200mm.json"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, report = runner.preflight_case(manifest, root, Path(temp_dir))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["derived"]["terrain_only_preparation"])
        self.assertGreater(report["derived"]["minimum_bin_travel_length_m"], 0.2)

    def test_axis_transform_and_centering(self):
        obj = """v 10 -1 -2
v 10 1 -2
v 10 1 2
v 10 -1 2
v 12 -1 -2
v 12 1 -2
v 12 1 2
v 12 -1 2
f 1 4 3
f 1 3 2
f 5 6 7
f 5 7 8
f 1 2 6
f 1 6 5
f 4 8 7
f 4 7 3
f 1 5 8
f 1 8 4
f 2 3 7
f 2 7 6
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.obj"
            target = Path(temp_dir) / "target.obj"
            source.write_text(obj)
            runner.normalize_obj(
                source,
                target,
                "cm",
                {"travel": "+z", "axle": "+x", "up": "+y"},
            )
            report = runner.inspect_obj(target)
        self.assertEqual(report["extents_m"], [0.04, 0.02, 0.02])
        self.assertTrue(report["watertight_two_manifold"])
        self.assertEqual(report["bounds_min_m"], [-0.02, -0.01, -0.01])
        self.assertEqual(report["bounds_max_m"], [0.02, 0.01, 0.01])

    def test_rejects_duplicate_source_axes(self):
        with self.assertRaises(runner.CaseError):
            runner.axis_transform({"travel": "+x", "axle": "+x", "up": "+z"})

    def test_slip_labels_do_not_collapse_distinct_cases(self):
        self.assertEqual(runner.slip_label(0.09396784087753285), "0.093968")
        self.assertNotEqual(runner.slip_label(0.08), runner.slip_label(0.12))

    def test_imported_wheel_bed_preserves_density_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text("X,Y,Z,clump_type\n0,0,0,t0\n")
            paths = {"terrain": root / "terrain"}
            config = SimpleNamespace(
                TERRAIN_INITIAL_STATE_CSV_st=str(source),
                TERRAIN_IMPORTED_PREPARATION_st={
                    "source_preparation_path": "/source/preparation.json",
                    "source_preparation_sha256": "abc123",
                    "target_bulk_density_kg_m3": 1703.2,
                    "post_release_bulk_density_kg_m3": 1654.2,
                },
            )
            runner.run_terrain(root, config, paths, overwrite=True)
            preparation = json.loads(
                (paths["terrain"] / "terrain_preparation.json").read_text()
            )
        self.assertEqual(preparation["target_bulk_density_kg_m3"], 1703.2)
        self.assertEqual(preparation["post_release_bulk_density_kg_m3"], 1654.2)

    def test_initial_state_case_id_resolves_inside_output_root(self):
        root = Path(__file__).resolve().parents[1]
        source_manifest = root / "cases" / "alabama_rider_smoke.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            state = (
                output_root
                / "fixed-bed"
                / "terrain"
                / "settled terrain data"
                / "settled_terrain_data.csv"
            )
            state.parent.mkdir(parents=True)
            state.write_text("X,Y,Z,clump_type\n0,0,0,t0\n")
            manifest = output_root / "portable.json"
            case = json.loads(source_manifest.read_text())
            case["case_id"] = "portable"
            case["terrain"]["initial_state_case_id"] = "fixed-bed"
            manifest.write_text(json.dumps(case))
            frozen, _, report = runner.preflight_case(manifest, root, output_root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(frozen["_resolved_initial_state_csv"], str(state))


if __name__ == "__main__":
    unittest.main()
