from dataclasses import dataclass
from typing import List, Optional

from summary_utils import compute_backtest_metrics


@dataclass
class BacktestResult:
    mae: float
    mape: float
    directional_accuracy: float
    interval_coverage: float


def evaluate_forecasts(
    actuals: List[Optional[float]],
    forecasts: List[Optional[float]],
    interval_low: Optional[List[Optional[float]]] = None,
    interval_high: Optional[List[Optional[float]]] = None,
) -> BacktestResult:
    """
    Lightweight backtest harness: score forecast vs actual arrays with optional intervals.
    """
    metrics = compute_backtest_metrics(actuals, forecasts, interval_low, interval_high)
    return BacktestResult(
        mae=metrics["mae"],
        mape=metrics["mape"],
        directional_accuracy=metrics["directional_accuracy"],
        interval_coverage=metrics["interval_coverage"],
    )
