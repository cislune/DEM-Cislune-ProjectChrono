import unittest

import cpt_reference as cpt


class CptReferenceTests(unittest.TestCase):
    def test_linear_fit(self):
        fit = cpt.linear_fit([(10.0, 25.0), (20.0, 45.0), (30.0, 65.0)])
        self.assertAlmostEqual(fit["slope_kpa_per_mm"], 2.0)
        self.assertAlmostEqual(fit["intercept_kpa"], 5.0)
        self.assertAlmostEqual(fit["r_squared"], 1.0)

    def test_extracts_four_profiles(self):
        cells = {}
        for row, depth in enumerate((10.0, 50.0, 100.0), 2):
            cells[(row, 0)] = depth
            for column in range(1, 5):
                cells[(row, column)] = depth * column
        profile = cpt.extract_sheet_profile(cells)
        self.assertEqual(len(profile["rows"]), 3)
        self.assertEqual(profile["aggregate"]["q_100mm_mean_kpa"], 250.0)
        self.assertEqual(profile["insertions"][3]["q_100mm_kpa"], 400.0)

    def test_extracts_density_metadata(self):
        cells = {}
        for row, depth in enumerate((10.0, 50.0, 100.0), 2):
            cells[(row, 0)] = depth
            for column in range(1, 5):
                cells[(row, column)] = depth * column
        cells[(10, 0)] = "Bulk Density (g/cm3)"
        for column, value in enumerate((1.6, 1.7, 1.8, 1.9), 1):
            cells[(10, column)] = value
        profile = cpt.extract_sheet_profile(cells)
        self.assertAlmostEqual(
            profile["metadata"]["bulk_density_g_cm3"]["mean"], 1.75
        )

    def test_interpolates(self):
        self.assertEqual(cpt.interpolate([(0.0, 0.0), (100.0, 400.0)], 25.0), 100.0)


if __name__ == "__main__":
    unittest.main()
