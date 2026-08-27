import unittest

import run_case_queue as queue


class RunCaseQueueTests(unittest.TestCase):
    def test_selection_is_one_based(self):
        self.assertEqual(queue.parse_selection("1,3", 4), [0, 2])

    def test_default_selects_all(self):
        self.assertEqual(queue.parse_selection(None, 3), [0, 1, 2])

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            queue.parse_selection("0", 3)


if __name__ == "__main__":
    unittest.main()
