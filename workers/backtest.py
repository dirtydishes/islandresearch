"""
Backtest scaffolding with as-of filtering.

This module loads canonical facts as-of a given date and reuses the summary-style
revenue backtest to produce quick validation metrics. Intended to expand into
time-travel harness coverage.
"""
from typing import Any, Dict, Optional
from datetime import date

from psycopg.rows import dict_row

from .db import ensure_schema, get_conn
from .tag_map import allowed_line_items, allowed_statements
def _filter_allowed(
    metrics: Dict[str, Dict[str, Dict[str, Any]]],
    allowed_items: Dict[str, set[str]],
) -> Dict[str, Dict[str, Any]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    for period, payload in metrics.items():
        values = payload.get("values", {})
        kept: Dict[str, Dict[str, Any]] = {}
        for line_item, val in values.items():
            if any(line_item in items for items in allowed_items.values()):
                kept[line_item] = val
        if kept:
            filtered[period] = {"period_end": payload.get("period_end", period), "values": kept}
    return filtered


def _compute_drivers(metrics: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Optional[float]]]:
    if not metrics:
        return {"revenue_growth": {"value": None}}
    sorted_periods = sorted(metrics.keys(), reverse=True)
    latest = sorted_periods[0]
    prev = sorted_periods[1] if len(sorted_periods) > 1 else None
    latest_revenue = metrics[latest]["values"].get("revenue", {}).get("value")
    prev_revenue = metrics.get(prev, {}).get("values", {}).get("revenue", {}).get("value") if prev else None
    revenue_growth = None
    if latest_revenue is not None and prev_revenue is not None and prev_revenue != 0:
        revenue_growth = (latest_revenue - prev_revenue) / prev_revenue
    if revenue_growth is None and latest_revenue is not None:
        revenue_growth = 0.02
    return {"revenue_growth": {"value": revenue_growth}}


def _compute_backtest_metrics(
    actuals: list[Optional[float]],
    forecasts: list[Optional[float]],
) -> Dict[str, float]:
    paired = [(a, f) for a, f in zip(actuals, forecasts) if a is not None and f is not None]
    if not paired:
        return {"mae": float("nan"), "mape": float("nan"), "directional_accuracy": float("nan"), "interval_coverage": float("nan")}
    mae = sum(abs(a - f) for a, f in paired) / len(paired)
    mape_vals = [abs(a - f) / abs(a) for a, f in paired if a not in (0, None)]
    mape = sum(mape_vals) / len(mape_vals) if mape_vals else float("nan")
    directional_hits = [1 for a, f in paired if (a >= 0 and f >= 0) or (a < 0 and f < 0)]
    directional_accuracy = sum(directional_hits) / len(paired)
    return {
        "mae": mae,
        "mape": mape,
        "directional_accuracy": directional_accuracy,
        "interval_coverage": float("nan"),
    }


def _compute_revenue_backtest(metrics: Dict[str, Dict[str, Dict[str, Any]]]) -> Optional[Dict[str, float]]:
    if not metrics or len(metrics) < 2:
        return None
    periods = sorted(metrics.keys())
    actuals: list[float] = []
    forecasts: list[float] = []
    for idx in range(1, len(periods)):
        prev_period = periods[idx - 1]
        curr_period = periods[idx]
        prev_metrics: Dict[str, Dict[str, Dict[str, Any]]] = {prev_period: metrics[prev_period]}
        if idx >= 2:
            prev_metrics[periods[idx - 2]] = metrics[periods[idx - 2]]
        drivers_prev = _compute_drivers(prev_metrics)
        prev_revenue = metrics[prev_period]["values"].get("revenue", {}).get("value")
        if prev_revenue is None:
            continue
        growth = drivers_prev.get("revenue_growth", {}).get("value") or 0.0
        forecast_revenue = prev_revenue * (1 + growth)
        actual_revenue = metrics[curr_period]["values"].get("revenue", {}).get("value")
        if actual_revenue is None:
            continue
        forecasts.append(forecast_revenue)
        actuals.append(actual_revenue)
    if not actuals or not forecasts:
        return None
    scored = _compute_backtest_metrics(actuals, forecasts)
    scored["samples"] = len(actuals)
    return scored


def load_metrics_asof(ticker: str, as_of: date) -> Dict[str, Dict[str, Any]]:
    """
    Load canonical facts for a ticker with period_end <= as_of and group into metrics.
    """
    ensure_schema()
    t = ticker.upper()
    allowed_items = allowed_line_items()
    allowed_statements = allowed_statements()
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT period_end, statement, line_item, value, unit
                FROM canonical_facts
                WHERE ticker = %s
                  AND period_end IS NOT NULL
                  AND period_end <= %s
                  AND statement = ANY(%s)
                  AND line_item = ANY(%s)
                ORDER BY period_end DESC;
                """,
                (t, as_of, list(allowed_statements), list({li for items in allowed_items.values() for li in items})),
            )
            rows = cur.fetchall()

    metrics: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        period = row["period_end"].isoformat() if row["period_end"] else "unknown"
        metrics.setdefault(period, {"period_end": period, "values": {}, "sources": {}})
        metrics[period]["values"][row["line_item"]] = {
            "value": float(row["value"]) if row["value"] is not None else None,
            "unit": row["unit"],
        }
    return _filter_allowed(metrics, allowed_items)


def backtest_revenue_asof(ticker: str, as_of: date) -> Optional[Dict[str, float]]:
    """
    Compute revenue backtest metrics using only data available as of `as_of`.
    """
    metrics = load_metrics_asof(ticker, as_of)
    return _compute_revenue_backtest(metrics)


def backtest_revenue_time_travel_from_metrics(
    metrics_full: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    """
    Walk forward through periods, forecasting each next revenue using only data
    available as of the prior period.
    """
    if not metrics_full or len(metrics_full) < 2:
        return None
    periods = sorted(metrics_full.keys())
    actuals = []
    forecasts = []
    for idx in range(1, len(periods)):
        as_of_period = periods[idx - 1]
        metrics_asof = {p: metrics_full[p] for p in periods[:idx]}
        drivers = _compute_drivers(metrics_asof)
        prev_revenue = metrics_asof[as_of_period]["values"].get("revenue", {}).get("value")
        if prev_revenue is None:
            continue
        growth = drivers.get("revenue_growth", {}).get("value") or 0.0
        forecast = prev_revenue * (1 + growth)
        actual = metrics_full[periods[idx]]["values"].get("revenue", {}).get("value")
        if actual is None:
            continue
        forecasts.append(forecast)
        actuals.append(actual)
    if not actuals or not forecasts:
        return None
    scored = _compute_backtest_metrics(actuals, forecasts)
    scored["samples"] = len(actuals)
    return scored


def backtest_revenue_time_travel(ticker: str) -> Optional[Dict[str, float]]:
    """
    Compute time-travel revenue backtest across all available periods for a ticker.
    """
    metrics_full = load_metrics_asof(ticker, date.max)
    return backtest_revenue_time_travel_from_metrics(metrics_full)
