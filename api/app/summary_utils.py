from typing import Dict, List, Optional, Tuple, Set
import datetime

# Allowed statements and line items mirrored from workers/tag_map.py
ALLOWED_STATEMENTS = {"income_statement", "balance_sheet", "cash_flow"}
ALLOWED_LINE_ITEMS = {
    "income_statement": {
        "revenue",
        "cogs",
        "gross_profit",
        "r_and_d",
        "sga",
        "operating_expenses",
        "operating_income",
        "interest_income",
        "interest_expense",
        "other_income_expense",
        "pre_tax_income",
        "income_tax_expense",
        "net_income",
        "ebitda",
        "total_expenses",
        "eps_basic",
        "eps_diluted",
        "shares_basic",
        "shares_diluted",
        "shares_outstanding",
    },
    "balance_sheet": {
        "cash",
        "short_term_investments",
        "long_term_investments",
        "accounts_receivable",
        "inventory",
        "prepaid_expenses",
        "other_assets_current",
        "assets_current",
        "other_assets_noncurrent",
        "assets_noncurrent",
        "assets",
        "ppe",
        "goodwill",
        "intangible_assets",
        "accounts_payable",
        "accrued_expenses",
        "deferred_revenue_current",
        "deferred_revenue_noncurrent",
        "other_liabilities_current",
        "liabilities_current",
        "other_liabilities_noncurrent",
        "liabilities_noncurrent",
        "liabilities",
        "debt_current",
        "debt_long_term",
        "equity",
        "retained_earnings",
        "treasury_stock",
        "minority_interest",
        "liabilities_equity",
    },
    "cash_flow": {
        "net_income",
        "depreciation_amortization",
        "stock_compensation",
        "change_working_capital",
        "cfo",
        "capex",
        "acquisitions",
        "cfi",
        "dividends_paid",
        "share_repurchases",
        "debt_issued",
        "debt_repaid",
        "cff",
        "fx_on_cash",
        "change_in_cash",
        "change_in_restricted_cash",
    },
}
LINE_ITEM_TO_STATEMENTS: Dict[str, Set[str]] = {}
for statement, items in ALLOWED_LINE_ITEMS.items():
    for line_item in items:
        LINE_ITEM_TO_STATEMENTS.setdefault(line_item, set()).add(statement)


def filter_allowed(metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Drop any line items not in the canonical schema and remove empty periods."""
    filtered: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for period, payload in metrics.items():
        values = payload.get("values", {})
        kept: Dict[str, Dict[str, Optional[float]]] = {}
        kept_sources: Dict[str, Dict[str, Optional[float]]] = {}
        for line_item, val in values.items():
            for stmt, allowed in ALLOWED_LINE_ITEMS.items():
                if line_item in allowed:
                    kept[line_item] = val
                    source = payload.get("sources", {}).get(line_item)
                    if source:
                        kept_sources[line_item] = source
                    break
        if kept:
            filtered[period] = {
                "period_end": payload.get("period_end", period),
                "values": kept,
                "sources": kept_sources,
            }
    return filtered


def compute_drivers(metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Dict]:
    """Compute simple drivers (growth, margins, shares) with provenance."""
    if not metrics:
        return {}
    sorted_periods = sorted(metrics.keys(), reverse=True)
    latest = sorted_periods[0]
    prev = sorted_periods[1] if len(sorted_periods) > 1 else None
    latest_values = metrics[latest]["values"]
    prev_values = metrics.get(prev, {}).get("values", {}) if prev else {}

    def get_value(values: Dict[str, Dict[str, Optional[float]]], key: str) -> Optional[float]:
        entry = values.get(key)
        if entry is None:
            return None
        return entry.get("value")  # type: ignore[return-value]

    latest_revenue = get_value(latest_values, "revenue")
    prev_revenue = get_value(prev_values, "revenue")

    revenue_growth = None
    revenue_sources: List[Dict[str, str]] = []
    if latest_revenue is not None and prev_revenue is not None and prev_revenue != 0:
        revenue_growth = (latest_revenue - prev_revenue) / prev_revenue
        revenue_sources = [
            {"line_item": "revenue", "period_end": latest},
            {"line_item": "revenue", "period_end": prev or ""},
        ]
    if revenue_growth is None and latest_revenue is not None:
        revenue_growth = 0.02
        revenue_sources = [{"line_item": "revenue", "period_end": latest, "note": "fallback_growth"}]

    gross_profit = get_value(latest_values, "gross_profit")
    operating_income = get_value(latest_values, "operating_income")
    net_income = get_value(latest_values, "net_income")
    cfo = get_value(latest_values, "cfo")
    cfi = get_value(latest_values, "cfi")
    shares_sources: List[Dict[str, str]] = []
    shares = None
    for key in ("shares_diluted", "shares_outstanding", "shares_basic"):
        candidate = get_value(latest_values, key)
        if candidate is not None:
            shares = candidate
            shares_sources = [{"line_item": key, "period_end": latest}]
            break

    def margin(num: Optional[float], den: Optional[float]) -> Optional[float]:
        if num is None or den is None or den == 0:
            return None
        return num / den

    gross_margin = margin(gross_profit, latest_revenue)
    op_margin = margin(operating_income, latest_revenue)
    net_margin = margin(net_income, latest_revenue)
    fcf_val = (cfo or 0) + (cfi or 0) if (cfo is not None or cfi is not None) else None
    fcf_margin = margin(fcf_val, latest_revenue) if fcf_val is not None else None

    drivers: Dict[str, Dict] = {
        "revenue_growth": {"value": revenue_growth, "sources": revenue_sources},
        "gross_margin": {
            "value": gross_margin,
            "sources": [{"line_item": "gross_profit", "period_end": latest}, {"line_item": "revenue", "period_end": latest}],
        },
        "operating_margin": {
            "value": op_margin,
            "sources": [{"line_item": "operating_income", "period_end": latest}, {"line_item": "revenue", "period_end": latest}],
        },
        "net_margin": {
            "value": net_margin,
            "sources": [{"line_item": "net_income", "period_end": latest}, {"line_item": "revenue", "period_end": latest}],
        },
        "fcf_margin": {
            "value": fcf_margin,
            "sources": [
                {"line_item": "cfo", "period_end": latest},
                {"line_item": "cfi", "period_end": latest},
                {"line_item": "revenue", "period_end": latest},
            ],
        },
        "shares": {"value": shares, "sources": shares_sources},
    }
    return drivers


def build_forecast(
    latest_period: str,
    latest_values: Dict[str, Dict[str, Optional[float]]],
    drivers: Dict[str, Dict],
) -> List[Dict]:
    """Build a simple T+1 forecast using drivers."""
    revenue = latest_values.get("revenue", {}).get("value")
    if revenue is None:
        return []

    growth = drivers.get("revenue_growth", {}).get("value") or 0.0
    gross_margin = drivers.get("gross_margin", {}).get("value")
    op_margin = drivers.get("operating_margin", {}).get("value")
    net_margin = drivers.get("net_margin", {}).get("value")
    fcf_margin = drivers.get("fcf_margin", {}).get("value")
    shares = drivers.get("shares", {}).get("value")

    next_revenue = revenue * (1 + growth)
    def project(margin_val: Optional[float]) -> Optional[float]:
        if margin_val is None:
            return None
        return next_revenue * margin_val

    next_gross_profit = project(gross_margin)
    next_operating_income = project(op_margin)
    next_net_income = project(net_margin)
    next_fcf = project(fcf_margin)
    next_eps = (next_net_income / shares) if (shares and next_net_income is not None) else None

    return [
        {
            "period_end": f"{latest_period} +1",
            "values": {
                "revenue": {"value": next_revenue, "unit": "USD"},
                "gross_profit": {"value": next_gross_profit, "unit": "USD"},
                "operating_income": {"value": next_operating_income, "unit": "USD"},
                "net_income": {"value": next_net_income, "unit": "USD"},
                "eps_diluted": {"value": next_eps, "unit": "USDPerShare"},
                "fcf": {"value": next_fcf, "unit": "USD"},
            },
            "assumptions": drivers,
        }
    ]


def compute_backtest_metrics(
    actuals: List[Optional[float]],
    forecasts: List[Optional[float]],
    interval_low: Optional[List[Optional[float]]] = None,
    interval_high: Optional[List[Optional[float]]] = None,
) -> Dict[str, float]:
    """Lightweight scoring helper for backtesting."""
    if len(actuals) != len(forecasts):
        raise ValueError("actuals and forecasts must be the same length")
    if interval_low and len(interval_low) != len(actuals):
        raise ValueError("interval_low must match length of actuals")
    if interval_high and len(interval_high) != len(actuals):
        raise ValueError("interval_high must match length of actuals")

    paired = [(a, f) for a, f in zip(actuals, forecasts) if a is not None and f is not None]
    if not paired:
        return {"mae": float("nan"), "mape": float("nan"), "directional_accuracy": float("nan"), "interval_coverage": float("nan")}

    abs_errors = [abs(a - f) for a, f in paired]
    mae = sum(abs_errors) / len(abs_errors)

    mape_denoms = [abs(a) for a, _ in paired if a not in (0, None)]
    mape_vals = [abs(a - f) / abs(a) for a, f in paired if a not in (0, None)]
    mape = sum(mape_vals) / len(mape_vals) if mape_vals else float("nan")

    directional_hits = [1 for a, f in paired if (a >= 0 and f >= 0) or (a < 0 and f < 0)]
    directional_accuracy = sum(directional_hits) / len(paired)

    coverage_points = []
    if interval_low and interval_high:
        for idx, (a, low, high) in enumerate(zip(actuals, interval_low, interval_high)):
            if a is None or low is None or high is None:
                continue
            coverage_points.append(1 if low <= a <= high else 0)
    interval_coverage = sum(coverage_points) / len(coverage_points) if coverage_points else float("nan")

    return {
        "mae": mae,
        "mape": mape,
        "directional_accuracy": directional_accuracy,
        "interval_coverage": interval_coverage,
    }


def compute_revenue_backtest(metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> Optional[Dict[str, float]]:
    """
    Build simple revenue forecasts from sequential periods and score against actuals.
    Uses drivers from the prior period (with fallback growth) to project the next.
    """
    if not metrics or len(metrics) < 2:
        return None

    periods = sorted(metrics.keys())
    actuals: List[float] = []
    forecasts: List[float] = []

    for idx in range(1, len(periods)):
        prev_period = periods[idx - 1]
        curr_period = periods[idx]
        prev_metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {prev_period: metrics[prev_period]}
        if idx >= 2:
            prev_metrics[periods[idx - 2]] = metrics[periods[idx - 2]]
        drivers_prev = compute_drivers(prev_metrics)

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
    scored = compute_backtest_metrics(actuals, forecasts)
    scored["samples"] = len(actuals)
    return scored


def compute_coverage(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
    applicable_by_period: Optional[Dict[str, Dict[str, Set[str]]]] = None,
) -> Dict[str, Dict]:
    """
    Compute coverage per period: expected vs found counts by statement and overall.
    Also returns missing line items per statement for quick debugging.
    """
    coverage: Dict[str, Dict] = {}
    for period, payload in metrics.items():
        if applicable_by_period and period in applicable_by_period:
            expected_items = {
                stmt: set(applicable_by_period[period].get(stmt, set())) for stmt in ALLOWED_STATEMENTS
            }
        else:
            expected_items = {stmt: set(items) for stmt, items in ALLOWED_LINE_ITEMS.items()}
        found_items = {stmt: set() for stmt in ALLOWED_STATEMENTS}
        values = payload.get("values", {})
        for line_item in values.keys():
            statements = LINE_ITEM_TO_STATEMENTS.get(line_item)
            if not statements:
                continue
            for stmt in statements:
                found_items[stmt].add(line_item)
                expected_items[stmt].add(line_item)
        found_by_stmt = {stmt: len(items) for stmt, items in found_items.items()}
        expected_by_stmt = {stmt: len(items) for stmt, items in expected_items.items()}
        missing_by_stmt = {stmt: sorted(expected_items[stmt] - found_items[stmt]) for stmt in expected_items.keys()}
        coverage[period] = {
            "period_end": payload.get("period_end", period),
            "total_found": sum(found_by_stmt.values()),
            "total_expected": sum(expected_by_stmt.values()),
            "by_statement": {
                stmt: {"found": found_by_stmt[stmt], "expected": expected_by_stmt[stmt]} for stmt in sorted(ALLOWED_STATEMENTS)
            },
            "missing": {stmt: missing_by_stmt.get(stmt, []) for stmt in sorted(ALLOWED_STATEMENTS)},
        }
    return coverage


def _parse_iso_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.split("T")[0])
    except Exception:
        return None


def _duration_days(start: Optional[str], end: Optional[str]) -> Optional[int]:
    start_date = _parse_iso_date(start)
    end_date = _parse_iso_date(end)
    if not start_date or not end_date:
        return None
    try:
        return (end_date - start_date).days
    except Exception:
        return None


def compute_tie_checks(metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Compute simple tie checks per period:
    - Balance sheet: assets vs liabilities + equity
    - Cash flow: cfo + cfi + cff vs change in cash between periods
    """
    ties: Dict[str, Dict[str, Optional[float]]] = {}
    ordered_periods = sorted(metrics.keys(), reverse=True)

    def quarterized(line_item: str, idx: int) -> Optional[float]:
        """
        If values are cumulative YTD (common in 10-Q cash flow statements), derive quarter flow by
        differencing the prior period when the period start is unchanged or durations lengthen.
        """
        period = ordered_periods[idx]
        current_vals = metrics[period]["values"]
        val = current_vals.get(line_item, {}).get("value")
        if val is None:
            return None
        start = current_vals.get(line_item, {}).get("start")
        end_date = period
        current_period_type = metrics[period].get("values", {}).get(line_item, {}).get("period_type") or "duration"
        prev_period = ordered_periods[idx + 1] if idx + 1 < len(ordered_periods) else None
        if not prev_period:
            return val

        prev_vals = metrics[prev_period]["values"]
        prev_val = prev_vals.get(line_item, {}).get("value")
        prev_start = prev_vals.get(line_item, {}).get("start")
        prev_period_type = metrics[prev_period].get("values", {}).get(line_item, {}).get("period_type") or "duration"
        if prev_val is None:
            return val

        # Treat identical or missing start dates on duration facts as cumulative YTD; subtract prior cumulative to get the quarter.
        if current_period_type == "duration" and prev_period_type == "duration" and (
            (start and prev_start and start == prev_start) or (start is None or prev_start is None)
        ):
            return val - prev_val

        # If the duration gets longer (e.g., 13 weeks -> 26 weeks) treat as cumulative.
        current_duration = _duration_days(start, end_date)
        prev_duration = _duration_days(prev_start, prev_period)
        if current_duration is not None and prev_duration is not None and current_duration > prev_duration + 7:
            return val - prev_val

        # If starts advance, keep the reported period value (already quarterly).
        return val

    for idx, period in enumerate(ordered_periods):
        payload = metrics[period]
        vals = payload.get("values", {})
        liabilities_equity = vals.get("liabilities_equity", {}).get("value")
        assets = vals.get("assets", {}).get("value")
        liabilities = vals.get("liabilities", {}).get("value")
        equity = vals.get("equity", {}).get("value")
        if liabilities_equity is not None and assets is not None:
            bs_delta = assets - liabilities_equity
        else:
            bs_delta = assets - (liabilities + equity) if None not in (assets, liabilities, equity) else None

        cfo = quarterized("cfo", idx)
        cfi = quarterized("cfi", idx)
        cff = quarterized("cff", idx)
        fx_on_cash = quarterized("fx_on_cash", idx) or 0
        change_rc = quarterized("change_in_restricted_cash", idx) or 0
        cf_sum = cfo + cfi + cff + fx_on_cash + change_rc if None not in (cfo, cfi, cff) else None

        prev_period = ordered_periods[idx + 1] if idx + 1 < len(ordered_periods) else None
        prev_cash = metrics.get(prev_period, {}).get("values", {}).get("cash", {}).get("value") if prev_period else None
        curr_cash = vals.get("cash", {}).get("value")
        cash_delta = vals.get("change_in_cash", {}).get("value") if vals.get("change_in_cash") else (
            curr_cash - prev_cash if None not in (curr_cash, prev_cash) else None
        )
        cf_tie = (cf_sum - cash_delta) if None not in (cf_sum, cash_delta) else None

        ties[period] = {
            "period_end": payload.get("period_end", period),
            "bs_tie": bs_delta,
            "cf_sum": cf_sum,
            "cash_delta": cash_delta,
            "cf_tie": cf_tie,
            # Only drive status from balance sheet tie to avoid noisy CF warnings.
            "status": "fail" if (bs_delta is not None and abs(bs_delta) > 1e-2) else "ok",
        }
    return ties
