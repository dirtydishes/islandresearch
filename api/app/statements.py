from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional

from .db import ensure_schema, get_conn

STATEMENT_DISPLAY_ORDER = {
    "income_statement": [
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
    ],
    "balance_sheet": [
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
    ],
    "cash_flow": [
        "net_income",
        "depreciation_amortization",
        "stock_compensation",
        "change_accounts_receivable",
        "change_inventory",
        "change_prepaid_expenses",
        "change_other_assets",
        "change_accounts_payable",
        "change_accrued_expenses",
        "change_deferred_revenue",
        "change_other_liabilities",
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
        "change_in_restricted_cash",
        "change_in_cash",
    ],
}

def _select_period_start(starts: List[date]) -> Optional[str]:
    if not starts:
        return None
    counts = Counter(starts)
    max_count = max(counts.values())
    candidates = [start for start, count in counts.items() if count == max_count]
    chosen = min(candidates)
    return chosen.isoformat()


def get_statements_for_ticker(ticker: str, limit: int = 8) -> Dict[str, Any]:
    ensure_schema()
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
                       fact.source_path,
                       COALESCE(fact.xbrl_tag, cf.source_xbrl_tag) AS source_xbrl_tag,
                       COALESCE(fact.context_ref, cf.source_context_ref) AS source_context_ref,
                       fil.form,
                       fil.filed_at
                FROM canonical_facts cf
                LEFT JOIN facts fact ON fact.id = cf.source_fact_id
                LEFT JOIN filings fil ON fil.accession = cf.accession
                WHERE cf.ticker = %s AND cf.period_end IS NOT NULL
                ORDER BY cf.period_end DESC, cf.statement, cf.line_item
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    period_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        period_end = row["period_end"]
        if not period_end:
            continue
        key = period_end.isoformat()
        if key not in period_map:
            period_map[key] = {"period_end": key, "period_start": None, "lines": {}, "_starts": []}
        period_start = row.get("period_start")
        if period_start:
            period_map[key]["_starts"].append(period_start)
        statement = row["statement"]
        if not statement:
            continue
        period_map[key]["lines"].setdefault(statement, []).append(
            {
                "line_item": row["line_item"],
                "value": float(row["value"]) if row["value"] is not None else None,
                "unit": row["unit"],
                "source_accession": row.get("accession"),
                "source_path": row.get("source_path"),
                "source_xbrl_tag": row.get("source_xbrl_tag"),
                "source_context_ref": row.get("source_context_ref"),
                "source_form": row.get("form"),
                "source_filed_at": row.get("filed_at").isoformat() if row.get("filed_at") else None,
            }
        )
    # Order line items for each statement using a stable display order.
    for period_data in period_map.values():
        period_data["period_start"] = _select_period_start(period_data.pop("_starts", []))
        ordered: Dict[str, list] = {}
        for stmt in STATEMENT_DISPLAY_ORDER.keys():
            items = period_data["lines"].get(stmt, [])
            order = STATEMENT_DISPLAY_ORDER.get(stmt, [])
            ordered[stmt] = sorted(
                items,
                key=lambda it: (
                    order.index(it["line_item"]) if it.get("line_item") in order else len(order),
                    it.get("line_item") or "",
                ),
            )
        period_data["lines"] = ordered

    periods: List[Dict[str, Any]] = [
        {
            "period_end": key,
            "period_start": lines.get("period_start"),
            "lines": lines["lines"],
        }
        for key, lines in sorted(period_map.items(), key=lambda kv: kv[0], reverse=True)
    ]
    return {"periods": periods[:limit]}
