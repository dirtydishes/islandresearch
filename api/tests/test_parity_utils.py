import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import unittest

from parity_utils import coverage_mismatches, period_start_consistent, statement_counts


class ParityUtilsTests(unittest.TestCase):
    def test_statement_counts(self) -> None:
        period = {
            "lines": {
                "income_statement": [{"line_item": "revenue"}],
                "balance_sheet": [{"line_item": "cash"}, {"line_item": "assets"}],
            }
        }
        counts, total = statement_counts(period)
        self.assertEqual(counts["income_statement"], 1)
        self.assertEqual(counts["balance_sheet"], 2)
        self.assertEqual(total, 3)

    def test_coverage_mismatches_empty(self) -> None:
        summary_period = {"period_end": "2024-12-31"}
        coverage = {
            "total_found": 3,
            "by_statement": {
                "income_statement": {"found": 1},
                "balance_sheet": {"found": 2},
            },
        }
        statement_period = {
            "period_end": "2024-12-31",
            "lines": {
                "income_statement": [{"line_item": "revenue"}],
                "balance_sheet": [{"line_item": "cash"}, {"line_item": "assets"}],
            },
        }
        self.assertEqual(coverage_mismatches(summary_period, coverage, statement_period), [])

    def test_coverage_mismatches_detects_total_and_statement(self) -> None:
        summary_period = {"period_end": "2024-12-31"}
        coverage = {
            "total_found": 4,
            "by_statement": {"income_statement": {"found": 2}},
        }
        statement_period = {
            "period_end": "2024-12-31",
            "lines": {"income_statement": [{"line_item": "revenue"}]},
        }
        mismatches = coverage_mismatches(summary_period, coverage, statement_period)
        self.assertTrue(any("total mismatch" in msg for msg in mismatches))
        self.assertTrue(any("income_statement mismatch" in msg for msg in mismatches))

    def test_period_start_consistent(self) -> None:
        values = {
            "revenue": {"start": "2024-01-01"},
            "net_income": {"start": "2024-01-01"},
            "cfo": {"start": "2024-01-01"},
        }
        ok, starts = period_start_consistent(values, ("revenue", "net_income", "cfo"))
        self.assertTrue(ok)
        self.assertEqual(starts["revenue"], "2024-01-01")

        values["cfo"]["start"] = "2024-02-01"
        ok, _ = period_start_consistent(values, ("revenue", "net_income", "cfo"))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
