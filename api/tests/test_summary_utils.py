import sys
from pathlib import Path

# Make app module importable when running tests from repo root.
sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import unittest

from summary_utils import build_forecast, compute_drivers, filter_allowed


class SummaryUtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "gross_profit": {"value": 40.0, "unit": "USD"},
                    "operating_income": {"value": 20.0, "unit": "USD"},
                    "net_income": {"value": 15.0, "unit": "USD"},
                    "cfo": {"value": 25.0, "unit": "USD"},
                    "cfi": {"value": -5.0, "unit": "USD"},
                    "shares_diluted": {"value": 10.0, "unit": "SHARES"},
                }
            },
            "2023-12-31": {"values": {"revenue": {"value": 80.0, "unit": "USD"}}},
        }

    def test_compute_drivers(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["revenue_growth"]["value"], 0.25)
        self.assertAlmostEqual(drivers["gross_margin"]["value"], 0.4)
        self.assertAlmostEqual(drivers["operating_margin"]["value"], 0.2)
        self.assertAlmostEqual(drivers["net_margin"]["value"], 0.15)
        self.assertAlmostEqual(drivers["fcf_margin"]["value"], 0.2)
        self.assertEqual(drivers["shares"]["value"], 10.0)

    def test_build_forecast(self) -> None:
        drivers = compute_drivers(self.metrics)
        latest_period = "2024-12-31"
        forecast = build_forecast(latest_period, self.metrics[latest_period]["values"], drivers)
        self.assertEqual(len(forecast), 1)
        values = forecast[0]["values"]
        self.assertAlmostEqual(values["revenue"]["value"], 125.0)
        self.assertAlmostEqual(values["gross_profit"]["value"], 50.0)
        self.assertAlmostEqual(values["operating_income"]["value"], 25.0)
        self.assertAlmostEqual(values["net_income"]["value"], 18.75)
        self.assertAlmostEqual(values["eps_diluted"]["value"], 1.875)

    def test_filter_allowed(self) -> None:
        noisy = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "unknown_metric": {"value": 5.0, "unit": "USD"},
                }
            }
        }
        filtered = filter_allowed(noisy)
        self.assertIn("revenue", filtered["2024-12-31"]["values"])
        self.assertNotIn("unknown_metric", filtered["2024-12-31"]["values"])


if __name__ == "__main__":
    unittest.main()
