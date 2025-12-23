import unittest

from workers.backtest import backtest_revenue_time_travel_from_metrics


class BacktestTimeTravelTests(unittest.TestCase):
    def test_time_travel_backtest_scores_forecasts(self) -> None:
        metrics = {
            "2023-12-31": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}},
            "2024-12-31": {"values": {"revenue": {"value": 120.0, "unit": "USD"}}},
            "2025-12-31": {"values": {"revenue": {"value": 150.0, "unit": "USD"}}},
        }
        scored = backtest_revenue_time_travel_from_metrics(metrics)
        self.assertIsNotNone(scored)
        assert scored is not None
        self.assertEqual(scored["samples"], 2)
        self.assertAlmostEqual(scored["mae"], 12.0)
        self.assertAlmostEqual(scored["directional_accuracy"], 1.0)

    def test_time_travel_backtest_requires_multiple_periods(self) -> None:
        metrics = {"2023-12-31": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}}}
        scored = backtest_revenue_time_travel_from_metrics(metrics)
        self.assertIsNone(scored)


if __name__ == "__main__":
    unittest.main()
