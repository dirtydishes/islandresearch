import sys
from pathlib import Path

# Make app module importable when running tests from repo root.
sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import unittest

from summary_utils import (
    build_forecast,
    compute_drivers,
    filter_allowed,
    compute_backtest_metrics,
    compute_revenue_backtest,
    compute_tie_checks,
)


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
                },
                "sources": {
                    "revenue": {"line_item": "revenue", "period_end": "2024-12-31"},
                    "unknown_metric": {"line_item": "unknown_metric", "period_end": "2024-12-31"},
                },
            },
            "2023-12-31": {
                "values": {
                    "unknown_metric": {"value": 5.0, "unit": "USD"},
                }
            }
        }
        filtered = filter_allowed(noisy)
        self.assertIn("revenue", filtered["2024-12-31"]["values"])
        self.assertNotIn("unknown_metric", filtered["2024-12-31"]["values"])
        self.assertIn("revenue", filtered["2024-12-31"]["sources"])
        self.assertNotIn("2023-12-31", filtered)

    def test_compute_drivers_fallback_growth_and_share_source(self) -> None:
        metrics = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 50.0, "unit": "USD"},
                    "gross_profit": {"value": 20.0, "unit": "USD"},
                    "operating_income": {"value": 10.0, "unit": "USD"},
                    "net_income": {"value": 8.0, "unit": "USD"},
                    "cfo": {"value": 12.0, "unit": "USD"},
                    "cfi": {"value": -2.0, "unit": "USD"},
                    "shares_basic": {"value": 4.0, "unit": "SHARES"},
                },
                "sources": {"revenue": {"line_item": "revenue", "period_end": "2024-12-31"}},
            }
        }
        filtered = filter_allowed(metrics)
        drivers = compute_drivers(filtered)
        self.assertAlmostEqual(drivers["revenue_growth"]["value"], 0.02)
        self.assertTrue(any(src.get("note") == "fallback_growth" for src in drivers["revenue_growth"]["sources"]))
        self.assertEqual(drivers["shares"]["value"], 4.0)
        self.assertEqual(drivers["shares"]["sources"][0]["line_item"], "shares_basic")

    def test_compute_backtest_metrics(self) -> None:
        actuals = [100.0, 120.0, 80.0]
        forecasts = [90.0, 130.0, 70.0]
        lower = [80.0, 110.0, 60.0]
        upper = [110.0, 140.0, 90.0]
        metrics = compute_backtest_metrics(actuals, forecasts, lower, upper)
        self.assertAlmostEqual(metrics["mae"], 10.0)
        self.assertAlmostEqual(metrics["mape"], (0.1 + (10.0 / 120.0) + (10.0 / 80.0)) / 3)
        self.assertAlmostEqual(metrics["directional_accuracy"], 1.0)
        self.assertAlmostEqual(metrics["interval_coverage"], 1.0)

    def test_backtest_metrics_len_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            compute_backtest_metrics([1.0], [1.0, 2.0])

    def test_compute_revenue_backtest(self) -> None:
        metrics = {
            "2023-12-31": {"values": {"revenue": {"value": 80.0, "unit": "USD"}}},
            "2024-12-31": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}},
            "2025-12-31": {"values": {"revenue": {"value": 120.0, "unit": "USD"}}},
        }
        backtest = compute_revenue_backtest(metrics)
        self.assertIsNotNone(backtest)
        assert backtest is not None
        self.assertEqual(backtest["samples"], 2)
        self.assertTrue(backtest["mae"] >= 0)

    def test_tie_checks_quarterizes_ytd_cash_flows(self) -> None:
        metrics = {
            "2024-07-27": {
                "values": {
                    "cfo": {"value": 100.0, "unit": "USD", "start": "2024-01-29"},
                    "cfi": {"value": -30.0, "unit": "USD", "start": "2024-01-29"},
                    "cff": {"value": -10.0, "unit": "USD", "start": "2024-01-29"},
                    "cash": {"value": 140.0, "unit": "USD"},
                    "change_in_cash": {"value": 25.0, "unit": "USD"},
                }
            },
            "2024-04-27": {
                "values": {
                    "cfo": {"value": 60.0, "unit": "USD", "start": "2024-01-29"},
                    "cfi": {"value": -20.0, "unit": "USD", "start": "2024-01-29"},
                    "cff": {"value": -5.0, "unit": "USD", "start": "2024-01-29"},
                    "cash": {"value": 100.0, "unit": "USD"},
                    "change_in_cash": {"value": 10.0, "unit": "USD"},
                }
            },
        }
        ties = compute_tie_checks(metrics)
        latest = ties["2024-07-27"]
        # Quarterized values: (100-60)=40, (-30 - -20)=-10, (-10 - -5)=-5, sum=25, change_in_cash=25 => cf_tie=0
        self.assertAlmostEqual(latest["cf_sum"], 25.0)
        self.assertAlmostEqual(latest["cash_delta"], 25.0)
        self.assertAlmostEqual(latest["cf_tie"], 0.0)


if __name__ == "__main__":
    unittest.main()
