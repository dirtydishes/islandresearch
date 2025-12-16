from typing import Any, Dict, List

from psycopg2.extras import RealDictCursor

from .db import ensure_schema, get_conn


def get_summary(ticker: str) -> Dict[str, Any]:
    ensure_schema()
    t = ticker.upper()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT period_end, statement, line_item, value, unit
                FROM canonical_facts
                WHERE ticker = %s
                  AND period_end IS NOT NULL
                  AND statement IN ('income_statement','balance_sheet','cash_flow')
                  AND line_item IN ('revenue','net_income','operating_income','gross_profit','cash','assets','liabilities','equity','cfo','cfi','cff','debt_long_term','debt_current')
                ORDER BY period_end DESC;
                """,
                (t,),
            )
            facts = cur.fetchall()

            cur.execute(
                """
                SELECT accession, form, filed_at, path
                FROM filings
                WHERE ticker = %s
                ORDER BY filed_at DESC NULLS LAST, created_at DESC
                LIMIT 5;
                """,
                (t,),
            )
            filings = cur.fetchall()

    # Group metrics by period_end.
    metrics: Dict[str, Dict[str, Any]] = {}
    for row in facts:
        period = row["period_end"].isoformat() if row["period_end"] else "unknown"
        metrics.setdefault(period, {"period_end": period, "values": {}})
        metrics[period]["values"][row["line_item"]] = {
            "value": float(row["value"]) if row["value"] is not None else None,
            "unit": row["unit"],
        }

    return {"ticker": t, "periods": list(metrics.values()), "filings": [dict(f) for f in filings]}
