import json
from pathlib import Path
import tempfile
import unittest

import rank_cpt_calibration as ranking


class RankCptCalibrationTests(unittest.TestCase):
    def test_ranks_lower_score_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, score in (("a", 2.0), ("b", 1.0)):
                case = root / name
                (case / "penetration").mkdir(parents=True)
                (case / "frozen_case.json").write_text(
                    json.dumps(
                        {
                            "terrain": {
                                "youngs_modulus_pa": 1e8,
                                "particle_friction": 0.5,
                                "rolling_resistance": 0.05,
                                "cohesion": 0.0,
                                "base_particle_radius_m": 0.002,
                            }
                        }
                    )
                )
                (case / "penetration" / "cpt_run_health.json").write_text(
                    json.dumps(
                        {
                            "case_id": name,
                            "status": "PASS",
                            "calibration": {
                                "score_lower_is_better": score,
                                "q_100mm_predicted_kpa": 100.0,
                                "q_100mm_observed_kpa": 200.0,
                                "q_100mm_ratio_predicted_to_observed": 0.5,
                                "predicted_fit_10_to_100mm": {"slope_kpa_per_mm": 1.0},
                                "observed_fit_10_to_100mm": {"slope_kpa_per_mm": 2.0},
                            },
                        }
                    )
                )
            rows = ranking.rank(root)
        self.assertEqual([row["case_id"] for row in rows], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
