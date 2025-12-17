from typing import Any, Dict, List

from .db import ensure_schema, get_conn


def list_facts_by_ticker(ticker: str) -> List[Dict[str, Any]]:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT accession, cik, ticker, period_end, period_type, statement, line_item, value, unit, source_path, created_at
                FROM facts
                WHERE ticker = %s
                ORDER BY created_at DESC
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]
