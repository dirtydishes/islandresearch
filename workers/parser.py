import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

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
    logger.info("Parsed %d facts from %s", inserted, html_path)
    return {"inserted": inserted}
