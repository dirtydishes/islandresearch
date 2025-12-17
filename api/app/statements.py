from typing import Any, Dict, List

from .db import ensure_schema, get_conn


def get_statements_for_ticker(ticker: str, limit: int = 8) -> Dict[str, Any]:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT period_end, statement, line_item, value, unit
                FROM canonical_facts
                WHERE ticker = %s AND period_end IS NOT NULL
                ORDER BY period_end DESC, statement, line_item
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
            period_map[key] = {"period_end": key, "lines": {}}
        statement = row["statement"]
        if not statement:
            continue
        period_map[key]["lines"].setdefault(statement, []).append(
            {"line_item": row["line_item"], "value": float(row["value"]) if row["value"] is not None else None, "unit": row["unit"]}
        )
    periods: List[Dict[str, Any]] = [
        {"period_end": key, "lines": lines["lines"]} for key, lines in sorted(period_map.items(), key=lambda kv: kv[0], reverse=True)
    ]
    return {"periods": periods[:limit]}
