import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import unittest

from backtest import BacktestResult, evaluate_forecasts


class BacktestHarnessTests(unittest.TestCase):
    def test_evaluate_forecasts_scores_arrays(self) -> None:
        actuals = [100.0, 120.0, 80.0]
        forecasts = [90.0, 125.0, 70.0]
        lows = [80.0, 110.0, 60.0]
        highs = [110.0, 135.0, 90.0]

        result = evaluate_forecasts(actuals, forecasts, lows, highs)
        self.assertIsInstance(result, BacktestResult)
        self.assertAlmostEqual(result.mae, (10 + 5 + 10) / 3)
        self.assertGreater(result.directional_accuracy, 0.0)
        self.assertEqual(result.interval_coverage, 1.0)

    def test_validate_lengths(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_forecasts([1.0], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
