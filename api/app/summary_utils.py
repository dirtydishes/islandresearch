from typing import Dict, List, Optional, Tuple

# Allowed statements and line items mirrored from workers/canonical.py
ALLOWED_STATEMENTS = {"income_statement", "balance_sheet", "cash_flow"}
ALLOWED_LINE_ITEMS = {
    "income_statement": {
        "revenue",
        "gross_profit",
        "operating_income",
        "pre_tax_income",
        "net_income",
        "total_expenses",
        "cogs",
        "r_and_d",
        "sga",
        "operating_expenses",
        "eps_basic",
        "eps_diluted",
        "shares_basic",
        "shares_diluted",
        "shares_outstanding",
    },
    "balance_sheet": {
        "assets",
        "assets_current",
        "liabilities",
        "liabilities_current",
        "debt_long_term",
        "debt_current",
        "cash",
        "short_term_investments",
        "ppe",
        "inventory",
        "accounts_receivable",
        "accounts_payable",
        "equity",
        "liabilities_equity",
    },
    "cash_flow": {
        "cfo",
        "cfi",
        "cff",
        "capex",
        "depreciation_amortization",
    },
}


def filter_allowed(metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Drop any line items not in the canonical schema."""
    filtered: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for period, payload in metrics.items():
        values = payload.get("values", {})
        kept: Dict[str, Dict[str, Optional[float]]] = {}
        for line_item, val in values.items():
            for stmt, allowed in ALLOWED_LINE_ITEMS.items():
                if line_item in allowed:
                    kept[line_item] = val
                    break
        filtered[period] = {"values": kept, "sources": payload.get("sources", {})}
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
    shares = (
        get_value(latest_values, "shares_diluted")
        or get_value(latest_values, "shares_outstanding")
        or get_value(latest_values, "shares_basic")
    )

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
        "shares": {"value": shares, "sources": [{"line_item": "shares_diluted", "period_end": latest}]},
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
