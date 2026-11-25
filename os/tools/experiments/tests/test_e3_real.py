import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'analysis'))
import e3_real


class PlanTests(unittest.TestCase):
    def test_default_is_six_cells(self):
        self.assertEqual(len(e3_real.plan(5)), 30)

    def test_load_filter_gives_three_cells(self):
        runs = e3_real.plan(5, ['B2_memrate_c23'])
        self.assertEqual(len(runs), 15)
        self.assertEqual({r[1] for r in runs}, {'B2_memrate_c23'})

    def test_policy_and_full_cell_filters(self):
        self.assertEqual(len(e3_real.plan(5, ['fifo-latest'])), 10)
        self.assertEqual(len(e3_real.plan(5, ['B0_idle/latest-latest'])), 5)

    def test_unknown_cell_rejected(self):
        with self.assertRaises(ValueError):
            e3_real.plan(1, ['B9_nope'])

    def test_order_is_reproducible(self):
        self.assertEqual(e3_real.plan(5, ['B2_memrate_c23']), e3_real.plan(5, ['B2_memrate_c23']))


if __name__ == '__main__':
    unittest.main()
