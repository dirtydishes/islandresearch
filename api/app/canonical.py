from typing import Any, Dict, List

from .db import ensure_schema, get_conn


def list_canonical_by_ticker(ticker: str) -> List[Dict[str, Any]]:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker,
                       cik,
                       accession,
                       period_end,
                       period_type,
                       statement,
                       line_item,
                       value,
                       unit,
                       source_fact_id,
                       source_xbrl_tag,
                       source_context_ref,
                       created_at
                FROM canonical_facts
                WHERE ticker = %s
                ORDER BY period_end DESC NULLS LAST, created_at DESC
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]
