import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .db import ensure_schema, get_conn
from .canonical import is_allowed
from .tag_map import TAG_MAP

logger = logging.getLogger(__name__)

ALLOWED_CONTEXT_AXES = {
    "us-gaap:StatementClassOfStockAxis",
    "us-gaap:StatementEquityComponentsAxis",
    "dei:LegalEntityAxis",
}
ANCHOR_LINE_ITEMS = {
    "income_statement": {"revenue", "net_income", "gross_profit", "operating_income"},
    "balance_sheet": {"assets", "equity", "liabilities_equity", "cash"},
    "cash_flow": {"cfo", "cfi", "cff", "net_income"},
}


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


def _normalize_unit(raw: Optional[str]) -> str:
    if not raw:
        return "USD"
    cleaned = raw.strip()
    if ":" in cleaned:
        cleaned = cleaned.split(":")[-1]
    cleaned = cleaned.replace(" ", "")
    lowered = cleaned.lower()
    if lowered in {"usd", "dollar"}:
        return "USD"
    if lowered in {"usdpershare", "usd/share", "usdperstock", "usdperstockunit"}:
        return "USDPERSHARE"
    if lowered in {"share", "shares"}:
        return "SHARES"
    return cleaned.upper()


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
def parse_inline_xbrl(html_content: bytes) -> List[Dict[str, Optional[str]]]:
    """Extract a small set of inline XBRL facts by tag name, including period info."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Build context map to resolve period_end and type.
    contexts: Dict[str, Dict[str, Optional[str]]] = {}
    fallback_period_end: Optional[str] = None
    fallback_period_type: Optional[str] = None
    for ctx in soup.find_all(True):
        if not ctx.name or not ctx.name.lower().endswith("context"):
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        segment = ctx.find(lambda t: t.name and t.name.lower().endswith("segment"))
        if segment:
            dims = {m.get("dimension") for m in segment.find_all(lambda t: t.name and t.name.lower().endswith("explicitmember"))}
            if any(dim not in ALLOWED_CONTEXT_AXES for dim in dims):
                continue
        period = ctx.find(lambda t: t.name and t.name.lower().endswith("period"))
        if not period:
            continue
        start_node = period.find(lambda t: t.name and t.name.lower().endswith("startdate"))
        end_node = period.find(lambda t: t.name and t.name.lower().endswith("enddate"))
        instant_node = period.find(lambda t: t.name and t.name.lower().endswith("instant"))
        start = start_node.get_text(strip=True) if start_node else None
        end = end_node.get_text(strip=True) if end_node else None
        instant = instant_node.get_text(strip=True) if instant_node else None
        if instant:
            contexts[ctx_id] = {"period_end": instant, "period_type": "instant"}
            if fallback_period_end is None:
                fallback_period_end = instant
                fallback_period_type = "instant"
        else:
            contexts[ctx_id] = {"period_end": end, "period_type": "duration", "start": start}
            # Prefer duration as fallback when available.
            fallback_period_end = end or fallback_period_end
            fallback_period_type = "duration" if end else fallback_period_type

    anchor_contexts = {stmt: set() for stmt in ANCHOR_LINE_ITEMS.keys()}
    for tag in soup.find_all():
        name = tag.get("name")
        if not name or name not in TAG_MAP:
            continue
        mapping_entry = TAG_MAP[name]
        mappings = mapping_entry if isinstance(mapping_entry, list) else [mapping_entry]
        ctx_ref = tag.get("contextref")
        if ctx_ref and ctx_ref not in contexts:
            continue
        for line_item, statement in mappings:
            if line_item in ANCHOR_LINE_ITEMS.get(statement, set()) and ctx_ref:
                anchor_contexts[statement].add(ctx_ref)

    facts: List[Dict[str, Optional[str]]] = []
    for tag in soup.find_all():
        name = tag.get("name")
        if not name or name not in TAG_MAP:
            continue
        mapping_entry = TAG_MAP[name]
        mappings = mapping_entry if isinstance(mapping_entry, list) else [mapping_entry]
        text = tag.get_text(strip=True)
        amount = _apply_scale(_parse_amount(text), tag.get("scale"))
        amount = _apply_decimals(amount, tag.get("decimals"))
        ctx_ref = tag.get("contextref")
        if ctx_ref and ctx_ref not in contexts:
            # Skip facts tied to disallowed/segment-heavy contexts.
            continue
        ctx_data = contexts.get(ctx_ref or "", {})
        period_end = ctx_data.get("period_end") or fallback_period_end
        period_start = ctx_data.get("start")
        period_type = ctx_data.get("period_type") or fallback_period_type or "unknown"
        unit = _normalize_unit(tag.get("unitref") or tag.get("unit") or "USD")
        for line_item, statement in mappings:
            anchors = anchor_contexts.get(statement, set())
            if anchors and line_item not in ANCHOR_LINE_ITEMS.get(statement, set()):
                if not ctx_ref or ctx_ref not in anchors:
                    continue
            facts.append(
                {
                    "line_item": line_item,
                    "statement": statement,
                    "value": amount,
                    "unit": unit,
                    "period_start": period_start,
                    "period_end": period_end,
                    "period_type": period_type,
                }
            )
    return facts


def persist_fact(
    accession: str,
    cik: str,
    ticker: str,
    period_start: Optional[str],
    period_end: Optional[str],
    line_item: str,
    value: Optional[float],
    unit: str = "USD",
    period_type: str = "duration",
    statement: str = "income_statement",
    source_path: Optional[str] = None,
) -> bool:
    ensure_schema()
    if not is_allowed(statement, line_item):
        logger.info("Dropping fact with disallowed line item %s/%s", statement, line_item)
        return False
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO facts (accession, cik, ticker, period_start, period_end, period_type, statement, line_item, value, unit, source_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    accession,
                    cik,
                    ticker.upper(),
                    period_start,
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
    return True


def parse_and_store(accession: str, cik: str, ticker: str, html_path: str) -> Dict[str, int]:
    """Parse a saved filing HTML and store a few demo facts."""
    if not os.path.isfile(html_path):
        raise FileNotFoundError(html_path)
    with open(html_path, "rb") as f:
        content = f.read()
    parsed_rows = parse_simple_table(content)
    inserted = 0
    dropped = 0
    if parsed_rows:
        for row in parsed_rows:
            for key in list(row.keys()):
                lowered = key.lower()
                if "revenue" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        if persist_fact(accession, cik, ticker, None, None, "revenue", value, source_path=html_path):
                            inserted += 1
                        else:
                            dropped += 1
                if "net income" in lowered or "net loss" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        if persist_fact(accession, cik, ticker, None, None, "net_income", value, source_path=html_path):
                            inserted += 1
                        else:
                            dropped += 1
                if "ebitda" in lowered:
                    value = _parse_amount(row[key])
                    if value is not None:
                        if persist_fact(accession, cik, ticker, None, None, "ebitda", value, source_path=html_path):
                            inserted += 1
                        else:
                            dropped += 1
    # XBRL path (primary)
    inline_facts = parse_inline_xbrl(content)
    for fact in inline_facts:
        if fact["value"] is None:
            continue
        line_item = fact["line_item"] or "unknown"
        statement = fact.get("statement") or "unknown"
        ok = persist_fact(
            accession,
            cik,
            ticker,
            fact.get("period_start"),
            fact.get("period_end"),
            line_item,
            fact["value"],
            unit=fact.get("unit") or "USD",
            period_type=fact.get("period_type") or "unknown",
            statement=statement,
            source_path=html_path,
        )
        if ok:
            inserted += 1
        else:
            dropped += 1

    logger.info("Parsed %d facts from %s (dropped %d disallowed)", inserted, html_path, dropped)
    return {"inserted": inserted, "dropped": dropped}
