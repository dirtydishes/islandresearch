from typing import Any, Dict, List, Optional

from .db import ensure_schema, get_conn
from .ticker_map import get_cik_for_ticker, get_coverage_status
from .summary_utils import (
    ALLOWED_LINE_ITEMS,
    ALLOWED_STATEMENTS,
    build_forecast,
    compute_drivers,
    compute_revenue_backtest,
    compute_tie_checks,
    compute_coverage,
    filter_allowed,
)


def get_summary(ticker: str) -> Dict[str, Any]:
    ensure_schema()
    t = ticker.upper()
    cik = get_cik_for_ticker(ticker)
    covered = get_coverage_status(ticker)
    allowed_line_items = sorted({item for items in ALLOWED_LINE_ITEMS.values() for item in items})
    allowed_statements = sorted(ALLOWED_STATEMENTS)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cf.period_start,
                       cf.period_end,
                       cf.statement,
                       cf.line_item,
                       cf.value,
                       cf.unit,
                       f.source_path
                FROM canonical_facts cf
                LEFT JOIN facts f ON f.id = cf.source_fact_id
                WHERE cf.ticker = %s
                  AND cf.period_end IS NOT NULL
                  AND cf.statement = ANY(%s)
                  AND cf.line_item = ANY(%s)
                ORDER BY cf.period_end DESC;
                """,
                (t, allowed_statements, allowed_line_items),
            )
            facts = cur.fetchall()

            cur.execute(
                """
                SELECT accession, form, filed_at, path
                FROM filings
                WHERE ticker = %s
                ORDER BY filed_at DESC NULLS LAST, created_at DESC
                LIMIT 5;
                """,
                (t,),
            )
            filings = cur.fetchall()

    # Group metrics by period_end.
    metrics: Dict[str, Dict[str, Any]] = {}
    for row in facts:
        period = row["period_end"].isoformat() if row["period_end"] else "unknown"
        metrics.setdefault(period, {"period_end": period, "values": {}, "sources": {}})
        metrics[period]["values"][row["line_item"]] = {
            "value": float(row["value"]) if row["value"] is not None else None,
            "unit": row["unit"],
            "start": row.get("period_start").isoformat() if row.get("period_start") else None,
        }
        metrics[period]["sources"][row["line_item"]] = {
            "period_end": period,
            "line_item": row["line_item"],
            "statement": row["statement"],
            "unit": row["unit"],
            "path": row.get("source_path"),
        }

    allowed_metrics = filter_allowed(metrics)

    def _get_latest_metric(name: str) -> Optional[float]:
        if not allowed_metrics:
            return None
        latest_period = sorted(allowed_metrics.keys(), reverse=True)[0]
        return allowed_metrics[latest_period]["values"].get(name, {}).get("value")  # type: ignore[index]

    # Derived metrics from the latest period.
    revenue = _get_latest_metric("revenue")
    net_income = _get_latest_metric("net_income")
    operating_income = _get_latest_metric("operating_income")
    gross_profit = _get_latest_metric("gross_profit")
    cfo = _get_latest_metric("cfo")
    cfi = _get_latest_metric("cfi")
    debt = (_get_latest_metric("debt_long_term") or 0) + (_get_latest_metric("debt_current") or 0)
    equity = _get_latest_metric("equity")
    liabilities = _get_latest_metric("liabilities")
    assets = _get_latest_metric("assets")
    shares_basic = _get_latest_metric("shares_basic")
    shares_diluted = _get_latest_metric("shares_diluted")

    derived = {
        "gross_margin": (gross_profit / revenue) if revenue and revenue != 0 else None,
        "operating_margin": (operating_income / revenue) if revenue and revenue != 0 else None,
        "net_margin": (net_income / revenue) if revenue and revenue != 0 else None,
        "fcf": (cfo or 0) + (cfi or 0) if (cfo is not None or cfi is not None) else None,
        "fcf_margin": ((cfo or 0) + (cfi or 0)) / revenue if revenue and revenue != 0 and (cfo is not None or cfi is not None) else None,
        "debt_to_equity": (debt / equity) if equity and equity != 0 else None,
        "liabilities_to_assets": (liabilities / assets) if liabilities is not None and assets else None,
        "eps_basic": (net_income / shares_basic) if net_income is not None and shares_basic else None,
        "eps_diluted": (net_income / shares_diluted) if net_income is not None and shares_diluted else None,
    }

    # Filter metrics to canonical schema and compute driver-based forecast.
    drivers = compute_drivers(allowed_metrics)
    backtest = compute_revenue_backtest(allowed_metrics)
    coverage = compute_coverage(allowed_metrics)
    ties = compute_tie_checks(allowed_metrics)
    forecast: List[Dict[str, Any]] = []
    if allowed_metrics:
        latest_period = sorted(allowed_metrics.keys(), reverse=True)[0]
        forecast = build_forecast(latest_period, allowed_metrics[latest_period]["values"], drivers)

    return {
        "ticker": t,
        "periods": list(allowed_metrics.values()),
        "filings": [dict(f) for f in filings],
        "covered": covered,
        "resolvable": cik is not None,
        "cik": cik,
        "derived": derived,
        "drivers": drivers,
        "forecast": forecast,
        "backtest": backtest,
        "coverage": coverage,
        "ties": ties,
    }
