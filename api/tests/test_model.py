import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import unittest

from model import _group_by_statement


class ModelGroupingTests(unittest.TestCase):
    def test_group_by_statement_includes_multi_statement_items(self) -> None:
        values = {
            "revenue": {"value": 100.0, "unit": "USD"},
            "net_income": {"value": 12.0, "unit": "USD"},
            "cash": {"value": 50.0, "unit": "USD"},
            "fcf": {"value": 8.0, "unit": "USD"},
            "unknown": {"value": 1.0, "unit": "USD"},
        }
        sources = {
            "revenue": {
                "path": "/storage/raw/demo.html",
                "statement": "income_statement",
                "line_item": "revenue",
                "period_end": "2024-12-31",
                "unit": "USD",
            }
        }
        grouped = _group_by_statement(values, sources=sources)
        self.assertIn("revenue", grouped["income_statement"])
        self.assertIn("net_income", grouped["income_statement"])
        self.assertIn("net_income", grouped["cash_flow"])
        self.assertIn("cash", grouped["balance_sheet"])
        self.assertIn("fcf", grouped["cash_flow"])
        self.assertNotIn("unknown", grouped["income_statement"])
        self.assertEqual(grouped["income_statement"]["revenue"]["source"]["path"], "/storage/raw/demo.html")


if __name__ == "__main__":
    unittest.main()
