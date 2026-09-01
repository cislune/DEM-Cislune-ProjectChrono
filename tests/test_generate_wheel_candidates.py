from pathlib import Path
import tempfile
import unittest

import generate_wheel_candidates as generator
from dem_case_runner import inspect_obj


class GenerateWheelCandidateTests(unittest.TestCase):
    def test_all_candidate_meshes_are_watertight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for spec in generator.CANDIDATES:
                vertices, faces = generator.build_mesh(spec, 48, 6)
                path = Path(temp_dir) / f"{spec.name}.obj"
                generator.write_obj(path, vertices, faces)
                report = inspect_obj(path)
                self.assertTrue(report["watertight_two_manifold"], spec.name)
                self.assertEqual(report["non_triangular_faces"], 0, spec.name)

    def test_bambu_scale_respects_220mm_envelope(self):
        for spec in generator.CANDIDATES:
            scaled = generator.scaled_spec(spec, 0.110)
            self.assertAlmostEqual(
                scaled.core_radius_m + scaled.feature_height_m, 0.110
            )

    def test_full_scale_quadrants_are_watertight_and_fit_256mm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for spec in generator.CANDIDATES:
                for quadrant in range(4):
                    vertices, faces = generator.build_sector_mesh(
                        spec,
                        quadrant * 3.141592653589793 / 2,
                        (quadrant + 1) * 3.141592653589793 / 2,
                        16,
                        4,
                    )
                    path = Path(temp_dir) / f"{spec.name}_{quadrant}.obj"
                    generator.write_obj(path, vertices, faces)
                    report = inspect_obj(path)
                    self.assertTrue(report["watertight_two_manifold"], path.name)
                    self.assertLessEqual(max(report["extents_m"]), 0.256, path.name)

    def test_wave_stays_inside_envelope(self):
        spec = generator.CANDIDATES[2]
        radii = [
            generator.outer_radius(spec, 2 * 3.141592653589793 * i / 1000, 0.0)
            for i in range(1000)
        ]
        self.assertGreaterEqual(min(radii), spec.core_radius_m)
        self.assertLessEqual(max(radii), spec.core_radius_m + spec.feature_height_m)

    def test_full_scale_bore_clears_recovered_rtgs_hub_envelope(self):
        self.assertGreater(
            2.0 * generator.CANDIDATE_BORE_RADIUS_M,
            generator.RTGS_HUB_REFERENCE_OD_M,
        )

    def test_tuned_low_grouser_reduces_feature_height_only(self):
        specs = {spec.name: spec for spec in generator.CANDIDATES}
        baseline = specs["low_grouser_16"]
        tuned = specs["low_grouser_16_10mm"]
        self.assertEqual(tuned.lobes, baseline.lobes)
        self.assertEqual(tuned.profile_exponent, baseline.profile_exponent)
        self.assertAlmostEqual(tuned.feature_height_m, 0.010)


if __name__ == "__main__":
    unittest.main()
