import datetime
from typing import Any, Dict, List, Optional, Set

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
                       cf.accession,
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
                LIMIT 20;
                """,
                (t,),
            )
            filings = cur.fetchall()

            # Group metrics by period_end.
            metrics: Dict[str, Dict[str, Any]] = {}
            accession_counts: Dict[str, Dict[str, int]] = {}
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
                accession = row.get("accession")
                if accession:
                    accession_counts.setdefault(period, {})
                    accession_counts[period][accession] = accession_counts[period].get(accession, 0) + 1

            allowed_metrics = filter_allowed(metrics)

            def _pick_accession(counts: Dict[str, int]) -> Optional[str]:
                if not counts:
                    return None
                return max(counts.items(), key=lambda item: (item[1], item[0]))[0]

            preferred_accessions = {period: _pick_accession(counts) for period, counts in accession_counts.items()}
            applicable_by_period: Dict[str, Dict[str, Set[str]]] = {}
            if allowed_metrics:
                period_dates: List[datetime.date] = []
                period_lookup: Dict[datetime.date, str] = {}
                for period in allowed_metrics.keys():
                    try:
                        parsed = datetime.date.fromisoformat(period)
                    except ValueError:
                        continue
                    period_dates.append(parsed)
                    period_lookup[parsed] = period
                    applicable_by_period[period] = {stmt: set() for stmt in ALLOWED_STATEMENTS}

                if period_dates:
                    cur.execute(
                        """
                        SELECT accession, period_end, statement, line_item
                        FROM facts
                        WHERE ticker = %s
                          AND period_end = ANY(%s)
                          AND statement = ANY(%s)
                          AND line_item = ANY(%s)
                          AND value IS NOT NULL
                        """,
                        (t, period_dates, allowed_statements, allowed_line_items),
                    )
                    fact_rows = cur.fetchall()
                    for row in fact_rows:
                        period_end = row.get("period_end")
                        if not period_end:
                            continue
                        period_key = period_lookup.get(period_end)
                        if not period_key:
                            continue
                        preferred_accession = preferred_accessions.get(period_key)
                        if preferred_accession and row.get("accession") != preferred_accession:
                            continue
                        stmt = row.get("statement")
                        line_item = row.get("line_item")
                        if stmt in ALLOWED_STATEMENTS and line_item in ALLOWED_LINE_ITEMS.get(stmt, set()):
                            applicable_by_period[period_key][stmt].add(line_item)

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
        "gross_margin": (gross_profit / revenue) if (revenue not in (None, 0) and gross_profit is not None) else None,
        "operating_margin": (operating_income / revenue) if (revenue not in (None, 0) and operating_income is not None) else None,
        "net_margin": (net_income / revenue) if (revenue not in (None, 0) and net_income is not None) else None,
        "fcf": (cfo or 0) + (cfi or 0) if (cfo is not None or cfi is not None) else None,
        "fcf_margin": ((cfo or 0) + (cfi or 0)) / revenue if (revenue not in (None, 0) and (cfo is not None or cfi is not None)) else None,
        "debt_to_equity": (debt / equity) if (equity not in (None, 0) and debt is not None) else None,
        "liabilities_to_assets": (liabilities / assets) if (liabilities is not None and assets not in (None, 0)) else None,
        "eps_basic": (net_income / shares_basic) if (net_income is not None and shares_basic not in (None, 0)) else None,
        "eps_diluted": (net_income / shares_diluted) if (net_income is not None and shares_diluted not in (None, 0)) else None,
    }

    # Filter metrics to canonical schema and compute driver-based forecast.
    drivers = compute_drivers(allowed_metrics)
    backtest = compute_revenue_backtest(allowed_metrics)
    coverage = compute_coverage(allowed_metrics, applicable_by_period)
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
