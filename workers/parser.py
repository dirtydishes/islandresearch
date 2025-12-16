import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .db import ensure_schema, get_conn

logger = logging.getLogger(__name__)


def _parse_amount(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").replace("$", "").strip()
    if cleaned in {"", "-"}:
        return None
    try:
        return float(cleaned.replace("(", "-").replace(")", ""))
    except ValueError:
        return None


def _apply_decimals(value: Optional[float], decimals: Optional[str]) -> Optional[float]:
    if value is None or decimals is None:
        return value
    if decimals in {"INF", "inf"}:
        return value
    try:
        d = int(decimals)
        return value  # decimals indicate precision, not scale; leave as-is.
    except ValueError:
        return value


def _apply_scale(value: Optional[float], scale: Optional[str]) -> Optional[float]:
    if value is None or scale is None:
        return value
    try:
        s = int(scale)
        return value * (10 ** s)
    except ValueError:
        return value


def parse_simple_table(html_content: bytes) -> List[Dict[str, Optional[str]]]:
    """Very naive parser for demo: looks for tables with revenue/ebitda/net income."""
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    results: List[Dict[str, Optional[str]]] = []
    for table in tables:
        header_text = table.get_text(" ", strip=True).lower()
        if not any(key in header_text for key in ["revenue", "net income", "net loss", "ebitda"]):
            continue
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [h.get_text(" ", strip=True) for h in rows[0].find_all(["td", "th"])]
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) != len(headers):
                continue
            row_map = dict(zip(headers, cells))
            results.append(row_map)
    return results


TARGET_TAGS: Dict[str, Tuple[str, str]] = {
    # Income statement
    "us-gaap:Revenues": ("revenue", "income_statement"),
    "us-gaap:SalesRevenueNet": ("revenue", "income_statement"),
    "us-gaap:GrossProfit": ("gross_profit", "income_statement"),
    "us-gaap:OperatingIncomeLoss": ("operating_income", "income_statement"),
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": (
        "pre_tax_income",
        "income_statement",
    ),
    "us-gaap:NetIncomeLoss": ("net_income", "income_statement"),
    "us-gaap:CostsAndExpenses": ("total_expenses", "income_statement"),
    "us-gaap:CostOfRevenue": ("cogs", "income_statement"),
    "us-gaap:ResearchAndDevelopmentExpense": ("r_and_d", "income_statement"),
    "us-gaap:SellingGeneralAndAdministrativeExpense": ("sga", "income_statement"),
    "us-gaap:EarningsPerShareBasic": ("eps_basic", "income_statement"),
    "us-gaap:EarningsPerShareDiluted": ("eps_diluted", "income_statement"),
    "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic": ("shares_basic", "income_statement"),
    "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding": ("shares_diluted", "income_statement"),
    # Balance sheet
    "us-gaap:Assets": ("assets", "balance_sheet"),
    "us-gaap:AssetsCurrent": ("assets_current", "balance_sheet"),
    "us-gaap:Liabilities": ("liabilities", "balance_sheet"),
    "us-gaap:LiabilitiesCurrent": ("liabilities_current", "balance_sheet"),
    "us-gaap:LongTermDebtNoncurrent": ("debt_long_term", "balance_sheet"),
    "us-gaap:LongTermDebtCurrent": ("debt_current", "balance_sheet"),
    "us-gaap:DebtCurrent": ("debt_current", "balance_sheet"),
    "us-gaap:DebtNoncurrent": ("debt_long_term", "balance_sheet"),
    "us-gaap:CashAndCashEquivalentsAtCarryingValue": ("cash", "balance_sheet"),
    "us-gaap:InventoriesNet": ("inventory", "balance_sheet"),
    "us-gaap:AccountsReceivableNetCurrent": ("accounts_receivable", "balance_sheet"),
    "us-gaap:AccountsPayableCurrent": ("accounts_payable", "balance_sheet"),
    "us-gaap:StockholdersEquity": ("equity", "balance_sheet"),
    "us-gaap:LiabilitiesAndStockholdersEquity": ("liabilities_equity", "balance_sheet"),
    # Cash flow
    "us-gaap:NetCashProvidedByUsedInOperatingActivities": ("cfo", "cash_flow"),
    "us-gaap:NetCashProvidedByUsedInInvestingActivities": ("cfi", "cash_flow"),
    "us-gaap:NetCashProvidedByUsedInFinancingActivities": ("cff", "cash_flow"),
    "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": ("cfo", "cash_flow"),
    "us-gaap:NetCashProvidedByUsedInInvestingActivitiesContinuingOperations": ("cfi", "cash_flow"),
    "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations": ("cff", "cash_flow"),
}


def parse_inline_xbrl(html_content: bytes) -> List[Dict[str, Optional[str]]]:
    """Extract a small set of inline XBRL facts by tag name, including period info."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Build context map to resolve period_end and type.
    contexts: Dict[str, Dict[str, Optional[str]]] = {}
    fallback_period_end: Optional[str] = None
    fallback_period_type: Optional[str] = None
    for ctx in soup.find_all("xbrli:context"):
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        # Skip contexts with segments to favor consolidated values.
        if ctx.find("xbrli:segment"):
            continue
        period = ctx.find("xbrli:period")
        start = period.find("xbrli:startdate").get_text(strip=True) if period and period.find("xbrli:startdate") else None
        end = period.find("xbrli:enddate").get_text(strip=True) if period and period.find("xbrli:enddate") else None
        instant = period.find("xbrli:instant").get_text(strip=True) if period and period.find("xbrli:instant") else None
        if instant:
            contexts[ctx_id] = {"period_end": instant, "period_type": "instant"}
            if fallback_period_end is None:
                fallback_period_end = instant
                fallback_period_type = "instant"
        else:
            contexts[ctx_id] = {"period_end": end, "period_type": "duration", "start": start}
            # Prefer duration as fallback.
            fallback_period_end = end or fallback_period_end
            fallback_period_type = "duration" if end else fallback_period_type

    def normalize_unit(raw: Optional[str]) -> str:
        if not raw:
            return "USD"
        return raw.upper()

    facts: List[Dict[str, Optional[str]]] = []
    for tag in soup.find_all():
        name = tag.get("name")
        if not name or name not in TARGET_TAGS:
            continue
        text = tag.get_text(strip=True)
        amount = _parse_amount(text)
        amount = _apply_scale(amount, tag.get("scale"))
        ctx_ref = tag.get("contextref")
        ctx_data = contexts.get(ctx_ref or "", {})
        period_end = ctx_data.get("period_end") or fallback_period_end
        period_type = ctx_data.get("period_type") or fallback_period_type or "unknown"
        unit = normalize_unit(tag.get("unitref") or tag.get("unit") or "USD")
        line_item, statement = TARGET_TAGS[name]
        facts.append(
            {
                "line_item": line_item,
                "statement": statement,
                "value": amount,
                "unit": unit,
                "period_end": period_end,
                "period_type": period_type,
            }
        )
    return facts


def persist_fact(
    accession: str,
    cik: str,
    ticker: str,
    period_end: Optional[str],
    line_item: str,
    value: Optional[float],
    unit: str = "USD",
    period_type: str = "duration",
    statement: str = "income_statement",
    source_path: Optional[str] = None,
) -> None:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO facts (accession, cik, ticker, period_end, period_type, statement, line_item, value, unit, source_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    accession,
                    cik,
                    ticker.upper(),
                    period_end,
                    period_type,
                    statement,
                    line_item,
                    value,
                    unit,
                    source_path,
                ),
            )
        conn.commit()


def parse_and_store(accession: str, cik: str, ticker: str, html_path: str) -> Dict[str, int]:
    """Parse a saved filing HTML and store a few demo facts."""
    if not os.path.isfile(html_path):
        raise FileNotFoundError(html_path)
    with open(html_path, "rb") as f:
        content = f.read()
    parsed_rows = parse_simple_table(content)
    inserted = 0
    if parsed_rows:
        for row in parsed_rows:
            for key in list(row.keys()):
                lowered = key.lower()
                if "revenue" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        persist_fact(accession, cik, ticker, None, "revenue", value, source_path=html_path)
                        inserted += 1
                if "net income" in lowered or "net loss" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        persist_fact(accession, cik, ticker, None, "net_income", value, source_path=html_path)
                        inserted += 1
                if "ebitda" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        persist_fact(accession, cik, ticker, None, "ebitda", value, source_path=html_path)
                        inserted += 1
    # XBRL path (primary)
    inline_facts = parse_inline_xbrl(content)
    for fact in inline_facts:
        if fact["value"] is None:
            continue
        line_item = fact["line_item"] or "unknown"
        statement = fact.get("statement") or "unknown"
        persist_fact(
            accession,
            cik,
            ticker,
            fact.get("period_end"),
            line_item,
            fact["value"],
            unit=fact.get("unit") or "USD",
            period_type=fact.get("period_type") or "unknown",
            statement=statement,
            source_path=html_path,
        )
        inserted += 1

    logger.info("Parsed %d facts from %s", inserted, html_path)
    return {"inserted": inserted}
