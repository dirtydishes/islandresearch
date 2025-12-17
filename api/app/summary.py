from typing import Any, Dict, List, Optional

from .db import ensure_schema, get_conn
from .ticker_map import get_cik_for_ticker, get_coverage_status
from .summary_utils import build_forecast, compute_drivers, filter_allowed


def get_summary(ticker: str) -> Dict[str, Any]:
    ensure_schema()
    t = ticker.upper()
    cik = get_cik_for_ticker(ticker)
    covered = get_coverage_status(ticker)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT period_end, statement, line_item, value, unit
                FROM canonical_facts
                WHERE ticker = %s
                  AND period_end IS NOT NULL
                  AND statement IN ('income_statement','balance_sheet','cash_flow')
                  AND line_item IN ('revenue','net_income','operating_income','gross_profit','cash','assets','liabilities','equity','cfo','cfi','cff','debt_long_term','debt_current')
                ORDER BY period_end DESC;
                """,
                (t,),
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
        }
        metrics[period]["sources"][row["line_item"]] = {
            "period_end": period,
            "line_item": row["line_item"],
            "statement": row["statement"],
            "unit": row["unit"],
        }

    def _get_latest_metric(name: str) -> Optional[float]:
        if not metrics:
            return None
        latest_period = sorted(metrics.keys(), reverse=True)[0]
        return metrics[latest_period]["values"].get(name, {}).get("value")  # type: ignore[index]

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
    allowed_metrics = filter_allowed(metrics)
    drivers = compute_drivers(allowed_metrics)
    forecast: List[Dict[str, Any]] = []
    if allowed_metrics:
        latest_period = sorted(allowed_metrics.keys(), reverse=True)[0]
        forecast = build_forecast(latest_period, allowed_metrics[latest_period]["values"], drivers)

    return {
        "ticker": t,
        "periods": list(metrics.values()),
        "filings": [dict(f) for f in filings],
        "covered": covered,
        "resolvable": cik is not None,
        "cik": cik,
        "derived": derived,
        "drivers": drivers,
        "forecast": forecast,
    }
