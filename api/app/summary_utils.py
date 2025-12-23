import datetime
import math
from typing import Any, Dict, List, Optional, Set

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


# Default driver assumptions when historical data is insufficient
DEFAULT_DRIVERS = {
    "revenue_growth": 0.02,  # 2% baseline growth
    "gross_margin": 0.40,
    "operating_margin": 0.15,
    "net_margin": 0.10,
    "tax_rate": 0.21,  # US corporate rate
    "capex_pct": 0.05,  # 5% of revenue
    "da_pct": 0.03,  # 3% of revenue
    "nwc_pct": 0.10,  # 10% of revenue
    "interest_rate": 0.05,  # 5% on debt
}

# Scenario perturbations (multipliers on growth, additive on margins)
SCENARIO_CONFIG = {
    "base": {"growth_mult": 1.0, "margin_adj": 0.0},
    "bull": {"growth_mult": 1.5, "margin_adj": 0.02},
    "bear": {"growth_mult": 0.5, "margin_adj": -0.02},
}


def filter_allowed(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
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


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    """Safe division returning None if invalid."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def _get_value(values: Dict[str, Any], key: str) -> Optional[float]:
    """Extract value from nested dict structure."""
    entry = values.get(key)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def _compute_growth(
    current: Optional[float], previous: Optional[float]
) -> Optional[float]:
    """Compute period-over-period growth rate."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous


def _avg_growth(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
    line_item: str,
    periods: int = 4,
) -> Optional[float]:
    """Compute average growth rate over recent periods."""
    sorted_periods = sorted(metrics.keys(), reverse=True)
    if len(sorted_periods) < 2:
        return None

    growths = []
    for i in range(min(periods, len(sorted_periods) - 1)):
        curr_val = _get_value(metrics[sorted_periods[i]]["values"], line_item)
        prev_val = _get_value(metrics[sorted_periods[i + 1]]["values"], line_item)
        g = _compute_growth(curr_val, prev_val)
        if g is not None and not math.isinf(g) and abs(g) < 10:  # Filter outliers
            growths.append(g)

    return sum(growths) / len(growths) if growths else None


def _avg_margin(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
    num_item: str,
    den_item: str,
    periods: int = 4,
) -> Optional[float]:
    """Compute average margin/ratio over recent periods."""
    sorted_periods = sorted(metrics.keys(), reverse=True)
    margins = []
    for i in range(min(periods, len(sorted_periods))):
        num_val = _get_value(metrics[sorted_periods[i]]["values"], num_item)
        den_val = _get_value(metrics[sorted_periods[i]]["values"], den_item)
        m = _safe_div(num_val, den_val)
        if m is not None and not math.isinf(m) and abs(m) < 10:  # Filter outliers
            margins.append(m)

    return sum(margins) / len(margins) if margins else None


def compute_drivers(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Dict[str, Dict]:
    """
    Compute comprehensive drivers for 3-statement model with provenance.

    Drivers computed:
    - revenue_growth: YoY or QoQ revenue growth (averaged over recent periods)
    - gross_margin: Gross profit / Revenue
    - operating_margin: Operating income / Revenue
    - net_margin: Net income / Revenue
    - cogs_pct: COGS / Revenue
    - rd_pct: R&D / Revenue
    - sga_pct: SG&A / Revenue
    - tax_rate: Income tax / Pre-tax income
    - capex_pct: Capex / Revenue (absolute value)
    - da_pct: D&A / Revenue
    - nwc_pct: Net working capital / Revenue
    - fcf_margin: FCF / Revenue
    - shares: Diluted shares outstanding
    """
    if not metrics:
        return {}

    sorted_periods = sorted(metrics.keys(), reverse=True)
    latest = sorted_periods[0]
    prev = sorted_periods[1] if len(sorted_periods) > 1 else None
    latest_values = metrics[latest]["values"]
    prev_values = metrics.get(prev, {}).get("values", {}) if prev else {}

    # Extract latest period values
    latest_revenue = _get_value(latest_values, "revenue")
    prev_revenue = _get_value(prev_values, "revenue")
    gross_profit = _get_value(latest_values, "gross_profit")
    cogs = _get_value(latest_values, "cogs")
    operating_income = _get_value(latest_values, "operating_income")
    net_income = _get_value(latest_values, "net_income")
    pre_tax_income = _get_value(latest_values, "pre_tax_income")
    income_tax = _get_value(latest_values, "income_tax_expense")
    r_and_d = _get_value(latest_values, "r_and_d")
    sga = _get_value(latest_values, "sga")
    cfo = _get_value(latest_values, "cfo")
    cfi = _get_value(latest_values, "cfi")
    capex = _get_value(latest_values, "capex")
    da = _get_value(latest_values, "depreciation_amortization")
    ppe = _get_value(latest_values, "ppe")

    # Working capital components
    accounts_receivable = _get_value(latest_values, "accounts_receivable")
    inventory = _get_value(latest_values, "inventory")
    accounts_payable = _get_value(latest_values, "accounts_payable")

    # Calculate net working capital (AR + Inventory - AP)
    nwc = None
    nwc_components = []
    if accounts_receivable is not None:
        nwc = (nwc or 0) + accounts_receivable
        nwc_components.append("accounts_receivable")
    if inventory is not None:
        nwc = (nwc or 0) + inventory
        nwc_components.append("inventory")
    if accounts_payable is not None:
        nwc = (nwc or 0) - accounts_payable
        nwc_components.append("accounts_payable")

    # Revenue growth with multi-period averaging
    revenue_growth = _avg_growth(metrics, "revenue", periods=4)
    revenue_sources: List[Dict[str, str]] = []
    if revenue_growth is not None:
        revenue_sources = [
            {"line_item": "revenue", "period_end": latest, "method": "avg_growth_4p"}
        ]
    else:
        # Fallback to single-period growth
        revenue_growth = _compute_growth(latest_revenue, prev_revenue)
        if revenue_growth is not None:
            revenue_sources = [
                {"line_item": "revenue", "period_end": latest},
                {"line_item": "revenue", "period_end": prev or ""},
            ]

    # Ultimate fallback
    if revenue_growth is None and latest_revenue is not None:
        revenue_growth = DEFAULT_DRIVERS["revenue_growth"]
        revenue_sources = [
            {"line_item": "revenue", "period_end": latest, "note": "fallback_growth"}
        ]

    # Shares (prefer diluted)
    shares = None
    shares_sources: List[Dict[str, str]] = []
    for key in ("shares_diluted", "shares_outstanding", "shares_basic"):
        candidate = _get_value(latest_values, key)
        if candidate is not None:
            shares = candidate
            shares_sources = [{"line_item": key, "period_end": latest}]
            break

    # Margins (use averaged where possible for stability)
    gross_margin = _avg_margin(metrics, "gross_profit", "revenue", 4) or _safe_div(
        gross_profit, latest_revenue
    )
    op_margin = _avg_margin(metrics, "operating_income", "revenue", 4) or _safe_div(
        operating_income, latest_revenue
    )
    net_margin = _avg_margin(metrics, "net_income", "revenue", 4) or _safe_div(
        net_income, latest_revenue
    )

    # Cost ratios
    cogs_pct = _avg_margin(metrics, "cogs", "revenue", 4) or _safe_div(
        cogs, latest_revenue
    )
    rd_pct = _avg_margin(metrics, "r_and_d", "revenue", 4) or _safe_div(
        r_and_d, latest_revenue
    )
    sga_pct = _avg_margin(metrics, "sga", "revenue", 4) or _safe_div(
        sga, latest_revenue
    )

    # Tax rate
    tax_rate = _safe_div(income_tax, pre_tax_income)
    if tax_rate is not None and (tax_rate < 0 or tax_rate > 0.5):
        tax_rate = DEFAULT_DRIVERS["tax_rate"]  # Use default for unusual rates

    # Capex as % of revenue (use absolute value since capex is negative outflow)
    capex_pct = None
    if capex is not None and latest_revenue:
        capex_pct = abs(capex) / latest_revenue
    elif cfi is not None and latest_revenue:
        # Approximate capex from CFI if direct capex not available
        capex_pct = abs(cfi) / latest_revenue * 0.7  # Assume 70% of CFI is capex

    # D&A as % of revenue
    da_pct = _safe_div(da, latest_revenue) if da else None
    if da_pct is None and ppe is not None and latest_revenue:
        # Estimate D&A as ~10% of PPE annually
        da_pct = (ppe * 0.10) / latest_revenue if latest_revenue else None

    # NWC as % of revenue
    nwc_pct = _safe_div(nwc, latest_revenue)

    # FCF margin
    fcf_val = None
    if cfo is not None and capex is not None:
        fcf_val = cfo + capex  # capex is negative
    elif cfo is not None and cfi is not None:
        fcf_val = cfo + cfi
    fcf_margin = _safe_div(fcf_val, latest_revenue)

    # Interest expense as % of debt
    interest_expense = _get_value(latest_values, "interest_expense")
    total_debt = (_get_value(latest_values, "debt_long_term") or 0) + (
        _get_value(latest_values, "debt_current") or 0
    )
    interest_rate = _safe_div(interest_expense, total_debt) if total_debt else None

    def make_source(
        items: List[str], period: str, method: Optional[str] = None
    ) -> List[Dict]:
        sources = [{"line_item": item, "period_end": period} for item in items]
        if method and sources:
            sources[0]["method"] = method
        return sources

    drivers: Dict[str, Dict] = {
        "revenue_growth": {
            "value": revenue_growth,
            "sources": revenue_sources,
            "description": "Revenue growth rate (averaged over 4 periods)",
        },
        "gross_margin": {
            "value": gross_margin,
            "sources": make_source(["gross_profit", "revenue"], latest, "avg_4p"),
            "description": "Gross profit as % of revenue",
        },
        "operating_margin": {
            "value": op_margin,
            "sources": make_source(["operating_income", "revenue"], latest, "avg_4p"),
            "description": "Operating income as % of revenue",
        },
        "net_margin": {
            "value": net_margin,
            "sources": make_source(["net_income", "revenue"], latest, "avg_4p"),
            "description": "Net income as % of revenue",
        },
        "cogs_pct": {
            "value": cogs_pct,
            "sources": make_source(["cogs", "revenue"], latest),
            "description": "COGS as % of revenue",
        },
        "rd_pct": {
            "value": rd_pct,
            "sources": make_source(["r_and_d", "revenue"], latest),
            "description": "R&D expense as % of revenue",
        },
        "sga_pct": {
            "value": sga_pct,
            "sources": make_source(["sga", "revenue"], latest),
            "description": "SG&A expense as % of revenue",
        },
        "tax_rate": {
            "value": tax_rate or DEFAULT_DRIVERS["tax_rate"],
            "sources": make_source(["income_tax_expense", "pre_tax_income"], latest),
            "description": "Effective tax rate",
            "is_default": tax_rate is None,
        },
        "capex_pct": {
            "value": capex_pct or DEFAULT_DRIVERS["capex_pct"],
            "sources": make_source(["capex", "revenue"], latest),
            "description": "Capex as % of revenue",
            "is_default": capex_pct is None,
        },
        "da_pct": {
            "value": da_pct or DEFAULT_DRIVERS["da_pct"],
            "sources": make_source(["depreciation_amortization", "revenue"], latest),
            "description": "D&A as % of revenue",
            "is_default": da_pct is None,
        },
        "nwc_pct": {
            "value": nwc_pct or DEFAULT_DRIVERS["nwc_pct"],
            "sources": make_source(
                nwc_components
                or ["accounts_receivable", "inventory", "accounts_payable"],
                latest,
            ),
            "description": "Net working capital as % of revenue",
            "is_default": nwc_pct is None,
        },
        "fcf_margin": {
            "value": fcf_margin,
            "sources": make_source(["cfo", "capex"], latest),
            "description": "Free cash flow as % of revenue",
        },
        "interest_rate": {
            "value": interest_rate or DEFAULT_DRIVERS["interest_rate"],
            "sources": make_source(
                ["interest_expense", "debt_long_term", "debt_current"], latest
            ),
            "description": "Interest rate on debt",
            "is_default": interest_rate is None,
        },
        "shares": {
            "value": shares,
            "sources": shares_sources,
            "description": "Diluted shares outstanding",
        },
    }

    return drivers


def _apply_scenario(drivers: Dict[str, Dict], scenario: str) -> Dict[str, float]:
    """Apply scenario adjustments to base drivers."""
    config = SCENARIO_CONFIG.get(scenario, SCENARIO_CONFIG["base"])

    adjusted = {}
    for key, driver in drivers.items():
        val = driver.get("value")
        if val is None:
            adjusted[key] = None
            continue

        if key == "revenue_growth":
            adjusted[key] = val * config["growth_mult"]
        elif key in ("gross_margin", "operating_margin", "net_margin", "fcf_margin"):
            # Margins: additive adjustment, bounded [0, 1]
            adjusted[key] = max(0, min(1, val + config["margin_adj"]))
        else:
            adjusted[key] = val

    return adjusted


def _next_period_end(period_end: str, periods_ahead: int = 1) -> str:
    """Generate next period end date string (assumes quarterly)."""
    try:
        dt = datetime.date.fromisoformat(period_end)
        # Add ~3 months per period (quarterly assumption)
        new_dt = dt + datetime.timedelta(days=91 * periods_ahead)
        return new_dt.isoformat()
    except ValueError:
        return f"{period_end} +{periods_ahead}"


def build_forecast(
    latest_period: str,
    latest_values: Dict[str, Dict[str, Optional[float]]],
    drivers: Dict[str, Dict],
    num_periods: int = 4,
    include_scenarios: bool = True,
) -> List[Dict]:
    """
    Build multi-period, multi-scenario forecast using driver-based 3-statement model.

    Generates:
    - Base case forecast for num_periods
    - Bull/bear scenarios if include_scenarios=True
    - Full P&L projection with tied metrics
    - Cash flow projection with FCF
    - Key balance sheet items

    All forecasted values include assumptions traceability.
    """
    revenue = _get_value(latest_values, "revenue")
    if revenue is None:
        return []

    # Extract driver values with defaults
    def get_driver(key: str, default: Optional[float] = None) -> Optional[float]:
        d = drivers.get(key, {})
        val = d.get("value")
        return val if val is not None else default

    base_growth = get_driver("revenue_growth", DEFAULT_DRIVERS["revenue_growth"])
    gross_margin = get_driver("gross_margin", DEFAULT_DRIVERS["gross_margin"])
    op_margin = get_driver("operating_margin", DEFAULT_DRIVERS["operating_margin"])
    net_margin = get_driver("net_margin", DEFAULT_DRIVERS["net_margin"])
    tax_rate = get_driver("tax_rate", DEFAULT_DRIVERS["tax_rate"])
    capex_pct = get_driver("capex_pct", DEFAULT_DRIVERS["capex_pct"])
    da_pct = get_driver("da_pct", DEFAULT_DRIVERS["da_pct"])
    nwc_pct = get_driver("nwc_pct", DEFAULT_DRIVERS["nwc_pct"])
    fcf_margin = get_driver("fcf_margin")
    shares = get_driver("shares")
    cogs_pct = get_driver("cogs_pct")
    rd_pct = get_driver("rd_pct")
    sga_pct = get_driver("sga_pct")

    # Starting balance sheet items
    starting_cash = _get_value(latest_values, "cash") or 0
    starting_ppe = _get_value(latest_values, "ppe") or 0

    scenarios_to_run = ["base"]
    if include_scenarios:
        scenarios_to_run = ["base", "bull", "bear"]

    forecasts = []

    for scenario_name in scenarios_to_run:
        adjusted = _apply_scenario(drivers, scenario_name)
        growth = adjusted.get("revenue_growth") or base_growth
        gm = adjusted.get("gross_margin") or gross_margin
        om = adjusted.get("operating_margin") or op_margin
        nm = adjusted.get("net_margin") or net_margin

        # Running values for balance sheet continuity
        running_cash = starting_cash
        running_ppe = starting_ppe
        running_revenue = revenue

        for period_idx in range(1, num_periods + 1):
            # Project revenue with compounding growth
            growth_rate = growth if growth is not None else 0.0
            projected_revenue = running_revenue * (1 + growth_rate)

            # Income Statement projections
            projected_gross_profit = projected_revenue * gm if gm else None

            # Build cost structure if we have detail, else use margins
            projected_cogs = projected_revenue * cogs_pct if cogs_pct else None
            if projected_cogs is None and projected_gross_profit is not None:
                projected_cogs = projected_revenue - projected_gross_profit

            projected_rd = projected_revenue * rd_pct if rd_pct else None
            projected_sga = projected_revenue * sga_pct if sga_pct else None

            projected_op_income = projected_revenue * om if om else None

            # Calculate operating expenses from detail or back out from margin
            projected_opex = None
            if projected_rd is not None and projected_sga is not None:
                projected_opex = projected_rd + projected_sga
            elif projected_gross_profit is not None and projected_op_income is not None:
                projected_opex = projected_gross_profit - projected_op_income

            # Pre-tax and net income
            projected_pre_tax = projected_op_income  # Simplified: ignore interest/other
            projected_tax = (
                projected_pre_tax * tax_rate if projected_pre_tax and tax_rate else None
            )

            projected_net_income = projected_revenue * nm if nm else None
            if (
                projected_net_income is None
                and projected_pre_tax is not None
                and projected_tax is not None
            ):
                projected_net_income = projected_pre_tax - projected_tax

            # EPS
            projected_eps = (
                projected_net_income / shares
                if (shares and projected_net_income)
                else None
            )

            # Cash Flow projections
            projected_da = projected_revenue * da_pct if da_pct else None
            projected_capex = (
                -(projected_revenue * capex_pct) if capex_pct else None
            )  # Negative outflow

            # Calculate FCF: Net Income + D&A - Capex - Change in NWC
            projected_nwc = projected_revenue * nwc_pct if nwc_pct else None
            prior_nwc = running_revenue * nwc_pct if nwc_pct else None
            delta_nwc = (
                (projected_nwc - prior_nwc)
                if (projected_nwc is not None and prior_nwc is not None)
                else 0
            )

            # FCF = NI + D&A + Capex (negative) - Delta NWC
            if projected_net_income is not None:
                projected_fcf = projected_net_income
                if projected_da:
                    projected_fcf += projected_da
                if projected_capex:
                    projected_fcf += projected_capex  # Already negative
                projected_fcf -= delta_nwc
            elif fcf_margin:
                projected_fcf = projected_revenue * fcf_margin
            else:
                projected_fcf = None

            # CFO approximation: NI + D&A - Delta NWC
            projected_cfo = None
            if projected_net_income is not None:
                projected_cfo = projected_net_income + (projected_da or 0) - delta_nwc

            # Balance Sheet updates
            if projected_fcf:
                running_cash = running_cash + projected_fcf
            if projected_capex and projected_da:
                running_ppe = (
                    running_ppe - projected_capex - projected_da
                )  # Capex is negative

            period_end_str = _next_period_end(latest_period, period_idx)

            forecast_entry = {
                "period_end": period_end_str,
                "scenario": scenario_name,
                "period_index": period_idx,
                "values": {
                    # Income Statement
                    "revenue": {"value": projected_revenue, "unit": "USD"},
                    "cogs": {"value": projected_cogs, "unit": "USD"},
                    "gross_profit": {"value": projected_gross_profit, "unit": "USD"},
                    "r_and_d": {"value": projected_rd, "unit": "USD"},
                    "sga": {"value": projected_sga, "unit": "USD"},
                    "operating_expenses": {"value": projected_opex, "unit": "USD"},
                    "operating_income": {"value": projected_op_income, "unit": "USD"},
                    "pre_tax_income": {"value": projected_pre_tax, "unit": "USD"},
                    "income_tax_expense": {"value": projected_tax, "unit": "USD"},
                    "net_income": {"value": projected_net_income, "unit": "USD"},
                    "eps_diluted": {"value": projected_eps, "unit": "USDPERSHARE"},
                    # Cash Flow
                    "depreciation_amortization": {"value": projected_da, "unit": "USD"},
                    "cfo": {"value": projected_cfo, "unit": "USD"},
                    "capex": {"value": projected_capex, "unit": "USD"},
                    "fcf": {"value": projected_fcf, "unit": "USD"},
                    # Balance Sheet (end of period)
                    "cash": {"value": running_cash, "unit": "USD"},
                    "ppe": {"value": running_ppe, "unit": "USD"},
                },
                "assumptions": {
                    "revenue_growth": growth,
                    "gross_margin": gm,
                    "operating_margin": om,
                    "net_margin": nm,
                    "tax_rate": tax_rate,
                    "capex_pct": capex_pct,
                    "da_pct": da_pct,
                    "nwc_pct": nwc_pct,
                    "shares": shares,
                },
                "driver_sources": {k: v.get("sources", []) for k, v in drivers.items()},
            }

            forecasts.append(forecast_entry)

            # Update running values for next period
            running_revenue = projected_revenue

    return forecasts


def build_forecast_summary(forecasts: List[Dict]) -> Dict[str, Any]:
    """
    Summarize multi-scenario forecasts into condensed prediction ranges.

    Returns prediction targets with point estimates and confidence bands.
    """
    if not forecasts:
        return {}

    # Group by period
    by_period: Dict[str, Dict[str, List[float]]] = {}
    for f in forecasts:
        period = f.get("period_end", "")
        scenario = f.get("scenario", "base")
        values = f.get("values", {})

        if period not in by_period:
            by_period[period] = {"revenue": [], "net_income": [], "eps": [], "fcf": []}

        for key, metric_key in [
            ("revenue", "revenue"),
            ("net_income", "net_income"),
            ("eps_diluted", "eps"),
            ("fcf", "fcf"),
        ]:
            val = values.get(key, {}).get("value")
            if val is not None:
                by_period[period][metric_key].append(val)

    # Build summary with ranges
    summary = {}
    for period, metrics in sorted(by_period.items()):
        period_summary = {}
        for metric, values in metrics.items():
            if not values:
                continue
            values_sorted = sorted(values)
            period_summary[metric] = {
                "point_estimate": values_sorted[len(values_sorted) // 2],  # median
                "low": values_sorted[0],
                "high": values_sorted[-1],
                "scenarios": len(values),
            }
        summary[period] = period_summary

    return summary


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

    paired = [
        (a, f) for a, f in zip(actuals, forecasts) if a is not None and f is not None
    ]
    if not paired:
        return {
            "mae": float("nan"),
            "mape": float("nan"),
            "directional_accuracy": float("nan"),
            "interval_coverage": float("nan"),
        }

    abs_errors = [abs(a - f) for a, f in paired]
    mae = sum(abs_errors) / len(abs_errors)

    mape_vals = [abs(a - f) / abs(a) for a, f in paired if a not in (0, None)]
    mape = sum(mape_vals) / len(mape_vals) if mape_vals else float("nan")

    directional_hits = [
        1 for a, f in paired if (a >= 0 and f >= 0) or (a < 0 and f < 0)
    ]
    directional_accuracy = sum(directional_hits) / len(paired)

    coverage_points = []
    if interval_low and interval_high:
        for idx, (a, low, high) in enumerate(zip(actuals, interval_low, interval_high)):
            if a is None or low is None or high is None:
                continue
            coverage_points.append(1 if low <= a <= high else 0)
    interval_coverage = (
        sum(coverage_points) / len(coverage_points) if coverage_points else float("nan")
    )

    return {
        "mae": mae,
        "mape": mape,
        "directional_accuracy": directional_accuracy,
        "interval_coverage": interval_coverage,
    }


def compute_revenue_backtest(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Optional[Dict[str, float]]:
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
        prev_metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {
            prev_period: metrics[prev_period]
        }
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


def compute_revenue_time_travel(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Optional[Dict[str, float]]:
    """
    Time-travel backtest: forecast each next period using only data available as of the prior period.
    """
    if not metrics or len(metrics) < 2:
        return None

    periods = sorted(metrics.keys())
    actuals: List[float] = []
    forecasts: List[float] = []

    for idx in range(1, len(periods)):
        as_of_period = periods[idx - 1]
        metrics_asof = {p: metrics[p] for p in periods[:idx]}
        drivers = compute_drivers(metrics_asof)
        prev_revenue = metrics_asof[as_of_period]["values"].get("revenue", {}).get("value")
        if prev_revenue is None:
            continue
        growth = drivers.get("revenue_growth", {}).get("value") or 0.0
        forecast = prev_revenue * (1 + growth)
        actual = metrics[periods[idx]]["values"].get("revenue", {}).get("value")
        if actual is None:
            continue
        forecasts.append(forecast)
        actuals.append(actual)

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
                stmt: set(applicable_by_period[period].get(stmt, set()))
                for stmt in ALLOWED_STATEMENTS
            }
        else:
            expected_items = {
                stmt: set(items) for stmt, items in ALLOWED_LINE_ITEMS.items()
            }
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
        missing_by_stmt = {
            stmt: sorted(expected_items[stmt] - found_items[stmt])
            for stmt in expected_items.keys()
        }
        coverage[period] = {
            "period_end": payload.get("period_end", period),
            "total_found": sum(found_by_stmt.values()),
            "total_expected": sum(expected_by_stmt.values()),
            "by_statement": {
                stmt: {"found": found_by_stmt[stmt], "expected": expected_by_stmt[stmt]}
                for stmt in sorted(ALLOWED_STATEMENTS)
            },
            "missing": {
                stmt: missing_by_stmt.get(stmt, [])
                for stmt in sorted(ALLOWED_STATEMENTS)
            },
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


def compute_tie_checks(
    metrics: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Dict[str, Dict[str, Optional[float]]]:
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
        current_period_type = (
            metrics[period].get("values", {}).get(line_item, {}).get("period_type")
            or "duration"
        )
        prev_period = (
            ordered_periods[idx + 1] if idx + 1 < len(ordered_periods) else None
        )
        if not prev_period:
            return val

        prev_vals = metrics[prev_period]["values"]
        prev_val = prev_vals.get(line_item, {}).get("value")
        prev_start = prev_vals.get(line_item, {}).get("start")
        prev_period_type = (
            metrics[prev_period].get("values", {}).get(line_item, {}).get("period_type")
            or "duration"
        )
        if prev_val is None:
            return val

        # Treat identical or missing start dates on duration facts as cumulative YTD; subtract prior cumulative to get the quarter.
        if (
            current_period_type == "duration"
            and prev_period_type == "duration"
            and (
                (start and prev_start and start == prev_start)
                or (start is None or prev_start is None)
            )
        ):
            return val - prev_val

        # If the duration gets longer (e.g., 13 weeks -> 26 weeks) treat as cumulative.
        current_duration = _duration_days(start, end_date)
        prev_duration = _duration_days(prev_start, prev_period)
        if (
            current_duration is not None
            and prev_duration is not None
            and current_duration > prev_duration + 7
        ):
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
            bs_delta = (
                assets - (liabilities + equity)
                if None not in (assets, liabilities, equity)
                else None
            )

        cfo = quarterized("cfo", idx)
        cfi = quarterized("cfi", idx)
        cff = quarterized("cff", idx)
        fx_on_cash = quarterized("fx_on_cash", idx) or 0
        change_rc = quarterized("change_in_restricted_cash", idx) or 0
        cf_sum = (
            cfo + cfi + cff + fx_on_cash + change_rc
            if None not in (cfo, cfi, cff)
            else None
        )

        prev_period = (
            ordered_periods[idx + 1] if idx + 1 < len(ordered_periods) else None
        )
        prev_cash = (
            metrics.get(prev_period, {}).get("values", {}).get("cash", {}).get("value")
            if prev_period
            else None
        )
        curr_cash = vals.get("cash", {}).get("value")
        cash_delta = (
            vals.get("change_in_cash", {}).get("value")
            if vals.get("change_in_cash")
            else (curr_cash - prev_cash if None not in (curr_cash, prev_cash) else None)
        )
        cf_tie = (cf_sum - cash_delta) if None not in (cf_sum, cash_delta) else None

        ties[period] = {
            "period_end": payload.get("period_end", period),
            "bs_tie": bs_delta,
            "cf_sum": cf_sum,
            "cash_delta": cash_delta,
            "cf_tie": cf_tie,
            # Only drive status from balance sheet tie to avoid noisy CF warnings.
            "status": "fail"
            if (bs_delta is not None and abs(bs_delta) > 1e-2)
            else "ok",
        }
    return ties
