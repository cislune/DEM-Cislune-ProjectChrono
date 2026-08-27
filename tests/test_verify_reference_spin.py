import math
import unittest

import numpy as np

from verify_reference_spin import infer_rigid_motion


class VerifyReferenceSpinTests(unittest.TestCase):
    def test_recovers_positive_y_rotation_and_translation(self):
        before = np.asarray(
            [
                [-1.0, -0.5, -1.0],
                [1.0, -0.5, -1.0],
                [1.0, 0.5, 1.0],
                [-1.0, 0.5, 1.0],
            ]
        )
        angle = 0.2
        rotation = np.asarray(
            [
                [math.cos(angle), 0.0, math.sin(angle)],
                [0.0, 1.0, 0.0],
                [-math.sin(angle), 0.0, math.cos(angle)],
            ]
        )
        translation = np.asarray([0.03, 0.0, -0.01])
        after = (rotation @ before.T).T + translation
        fitted_rotation, fitted_translation, residual = infer_rigid_motion(before, after)
        self.assertAlmostEqual(math.atan2(fitted_rotation[0, 2], fitted_rotation[0, 0]), angle)
        np.testing.assert_allclose(fitted_translation, translation, atol=1e-12)
        self.assertLess(residual, 1e-12)


if __name__ == "__main__":
    unittest.main()
