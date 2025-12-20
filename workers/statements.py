from collections import defaultdict
from typing import Any, Dict, List

from .db import ensure_schema, get_conn
from .tag_map import STATEMENT_DISPLAY_ORDER


Line = Dict[str, Any]
Period = Dict[str, Any]


def build_statements(ticker: str, max_periods: int = 8) -> Dict[str, List[Period]]:
    """Group canonical facts into simple statements keyed by period_end."""
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

    period_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"period_end": None, "lines": defaultdict(list)})
    for period_end, statement, line_item, value, unit in rows:
        key = period_end.isoformat()
        period_entry = period_map[key]
        period_entry["period_end"] = period_end.isoformat()
        if statement is None or line_item is None:
            continue
        period_entry["lines"][statement].append({"line_item": line_item, "value": float(value) if value is not None else None, "unit": unit})

    # Convert to list sorted by period_end desc and limit.
    periods: List[Period] = []
    for _, data in sorted(period_map.items(), key=lambda kv: kv[0], reverse=True):
        ordered_lines: Dict[str, list] = {}
        for stmt, items in data["lines"].items():
            order = STATEMENT_DISPLAY_ORDER.get(stmt, [])
            ordered_lines[stmt] = sorted(
                items,
                key=lambda it: (
                    order.index(it["line_item"]) if it.get("line_item") in order else len(order),
                    it.get("line_item") or "",
                ),
            )
        data["lines"] = ordered_lines
        periods.append(data)
    return {"periods": periods[:max_periods]}
