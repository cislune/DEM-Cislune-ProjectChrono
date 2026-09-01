import unittest
from unittest.mock import patch

import run_case_queue as queue


class RunCaseQueueTests(unittest.TestCase):
    def test_selection_is_one_based(self):
        self.assertEqual(queue.parse_selection("1,3", 4), [0, 2])

    def test_default_selects_all(self):
        self.assertEqual(queue.parse_selection(None, 3), [0, 1, 2])

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            queue.parse_selection("0", 3)

    def test_stage_defaults_to_all(self):
        with patch("sys.argv", ["run_case_queue.py", "queue.json", "--kind", "wheel"]):
            self.assertEqual(queue.parse_args().stage, "all")

    def test_terrain_stage_is_selectable(self):
        with patch(
            "sys.argv",
            ["run_case_queue.py", "queue.json", "--kind", "wheel", "--stage", "terrain"],
        ):
            self.assertEqual(queue.parse_args().stage, "terrain")

    def test_wall_time_cap_is_parsed(self):
        with patch(
            "sys.argv",
            ["run_case_queue.py", "queue.json", "--kind", "wheel", "--max-wall-s", "300"],
        ):
            self.assertEqual(queue.parse_args().max_wall_s, 300)


if __name__ == "__main__":
    unittest.main()
