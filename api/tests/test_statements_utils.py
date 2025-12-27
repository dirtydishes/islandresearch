import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import unittest

from app.statements import _select_period_start


class StatementUtilsTests(unittest.TestCase):
    def test_select_period_start_empty(self) -> None:
        self.assertIsNone(_select_period_start([]))

    def test_select_period_start_picks_most_common(self) -> None:
        starts = [date(2024, 1, 1), date(2024, 1, 1), date(2024, 4, 1)]
        self.assertEqual(_select_period_start(starts), "2024-01-01")

    def test_select_period_start_breaks_ties_by_earliest(self) -> None:
        starts = [date(2024, 4, 1), date(2024, 1, 1), date(2024, 4, 1), date(2024, 1, 1)]
        self.assertEqual(_select_period_start(starts), "2024-01-01")


if __name__ == "__main__":
    unittest.main()
