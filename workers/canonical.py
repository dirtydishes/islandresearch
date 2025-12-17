from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import ensure_schema, get_conn

# Supported statements and line items for canonical rows. Extend as coverage grows.
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


def is_allowed(statement: Optional[str], line_item: Optional[str]) -> bool:
    if not statement or not line_item:
        return False
    if statement not in ALLOWED_STATEMENTS:
        return False
    allowed = ALLOWED_LINE_ITEMS.get(statement, set())
    return line_item in allowed


def _normalize_period_type(statement: Optional[str], period_type: Optional[str]) -> str:
    if statement in ("income_statement", "cash_flow"):
        return "duration"
    if statement == "balance_sheet":
        return "instant"
    return period_type or "unknown"


def _normalize_unit(unit: Optional[str]) -> str:
    if not unit:
        return "USD"
    return unit.strip().upper()


def aggregate_canonical_rows(rows: Iterable[Dict[str, Any]], default_period_end: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Pure helper to aggregate fact rows by period/tag/unit.
    - Drops rows without value/statement/line_item.
    - Uses default_period_end when period_end is missing.
    - Normalizes period_type by statement.
    - Filters to allowed statements/line items.
    """
    aggregated: Dict[Tuple[Any, Any, Any, str, str, str, str], Dict[str, Any]] = {}
    for row in rows:
        value = row.get("value")
        statement = row.get("statement")
        line_item = row.get("line_item")
        if not is_allowed(statement, line_item):
            continue
        period_end = row.get("period_end") or default_period_end
        if value is None or not statement or not line_item or period_end is None:
            continue
        ticker = (row.get("ticker") or "").upper()
        cik = row.get("cik")
        accession = row.get("accession")
        period_type = _normalize_period_type(statement, row.get("period_type"))
        unit = _normalize_unit(row.get("unit"))
        key = (ticker, cik, period_end, period_type, statement, line_item, unit)
        existing = aggregated.get(key)
        numeric_value = float(value)
        source_id = row.get("id")
        if not existing:
            aggregated[key] = {
                "ticker": ticker,
                "cik": cik,
                "accession": accession,
                "period_end": period_end,
                "period_type": period_type,
                "statement": statement,
                "line_item": line_item,
                "value": numeric_value,
                "unit": unit,
                "source_fact_id": source_id,
            }
            continue
        existing["value"] = max(existing["value"], numeric_value)
        if accession:
            existing["accession"] = max(existing.get("accession"), accession)
        if source_id is not None:
            existing["source_fact_id"] = (
                existing["source_fact_id"] if existing["source_fact_id"] is not None else source_id
            )
            if existing["source_fact_id"] is not None:
                existing["source_fact_id"] = min(existing["source_fact_id"], source_id)
    return [aggregated[k] for k in sorted(aggregated.keys(), key=lambda x: (x[2], x[4], x[5]))]


def _infer_default_period_end(cur, ticker: str) -> Optional[Any]:
    cur.execute(
        """
        WITH latest AS (
          SELECT accession, MAX(created_at) AS created_at
          FROM facts
          WHERE ticker = %s
          GROUP BY accession
          ORDER BY created_at DESC
          LIMIT 1
        ),
        inferred_period AS (
          SELECT COALESCE(MAX(period_end), MAX(filed_at)) AS period_end
          FROM filings f
          JOIN latest l ON f.accession = l.accession
          WHERE f.ticker = %s
        )
        SELECT period_end FROM inferred_period;
        """,
        (ticker, ticker),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row[0]


def materialize_canonical_for_ticker(ticker: str) -> int:
    """
    Aggregate facts by period and line item so each period has a single normalized value per tag.
    """
    # Import here to avoid hard dependency during pure aggregation tests.
    from psycopg.rows import dict_row

    ensure_schema()
    inserted = 0
    t = ticker.upper()
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, ticker, cik, accession, period_end, period_type, statement, line_item, value, unit
                FROM facts
                WHERE ticker = %s
                  AND value IS NOT NULL
                  AND statement IS NOT NULL
                  AND line_item IS NOT NULL
                """,
                (t,),
            )
            fact_rows = cur.fetchall()

            cur.execute("DELETE FROM canonical_facts WHERE ticker = %s", (t,))

            aggregated = aggregate_canonical_rows(fact_rows)
            if not aggregated:
                default_period_end = _infer_default_period_end(cur, t)
                aggregated = aggregate_canonical_rows(fact_rows, default_period_end=default_period_end)

            if aggregated:
                insert_sql = """
                INSERT INTO canonical_facts (ticker, cik, accession, period_end, period_type, statement, line_item, value, unit, source_fact_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = [
                    (
                        row["ticker"],
                        row.get("cik"),
                        row.get("accession"),
                        row.get("period_end"),
                        row.get("period_type"),
                        row.get("statement"),
                        row.get("line_item"),
                        row.get("value"),
                        row.get("unit"),
                        row.get("source_fact_id"),
                    )
                    for row in aggregated
                ]
                cur.executemany(insert_sql, params)
                inserted = cur.rowcount
        conn.commit()
    return inserted
