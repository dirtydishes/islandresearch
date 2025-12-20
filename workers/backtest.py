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
from api.app.summary_utils import compute_revenue_backtest, filter_allowed  # type: ignore


def load_metrics_asof(ticker: str, as_of: date) -> Dict[str, Dict[str, Any]]:
    """
    Load canonical facts for a ticker with period_end <= as_of and group into metrics.
    """
    ensure_schema()
    t = ticker.upper()
    allowed_line_items = allowed_line_items()
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
                (t, as_of, list(allowed_statements), list({li for items in allowed_line_items.values() for li in items})),
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
    return filter_allowed(metrics)


def backtest_revenue_asof(ticker: str, as_of: date) -> Optional[Dict[str, float]]:
    """
    Compute revenue backtest metrics using only data available as of `as_of`.
    """
    metrics = load_metrics_asof(ticker, as_of)
    return compute_revenue_backtest(metrics)
