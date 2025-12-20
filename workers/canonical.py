import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import ensure_schema, get_conn
from .tag_map import allowed_line_items, allowed_statements

ALLOWED_STATEMENTS = allowed_statements()
ALLOWED_LINE_ITEMS = allowed_line_items()
import os

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default

TIE_TOLERANCE = _env_float("TIE_TOLERANCE", 1e-2)  # absolute tolerance for tie checks
HARD_FAIL_TIES = os.getenv("HARD_FAIL_TIES", "false").lower() in {"1", "true", "yes"}

logger = logging.getLogger(__name__)


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
    - Prefers facts from the latest accession when duplicates exist.
    - Computes basic tie checks (A=L+E, CFO/CFI/CFF sum) per period for downstream reporting.
    """
    aggregated: Dict[Tuple[Any, Any, Any, str, str, str, str], Dict[str, Any]] = {}
    for row in rows:
        value = row.get("value")
        statement = row.get("statement")
        line_item = row.get("line_item")
        if not is_allowed(statement, line_item):
            continue
        period_end = row.get("period_end") or default_period_end
        period_start = row.get("period_start")
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
                "period_start": period_start,
                "period_end": period_end,
                "period_type": period_type,
                "statement": statement,
                "line_item": line_item,
                "value": numeric_value,
                "unit": unit,
                "source_fact_id": source_id,
            }
            continue
        choose_current = False
        if accession and existing.get("accession"):
            choose_current = accession > existing["accession"]
        elif accession and not existing.get("accession"):
            choose_current = True

        current_value = existing.get("value")
        if choose_current:
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
        else:
            if statement == "cash_flow":
                # Prefer the shortest duration (closest start to end) when period_start present; fallback to smaller magnitude.
                def duration_days(ps, pe):
                    if ps is None or pe is None:
                        return None
                    try:
                        return (pe - ps).days
                    except Exception:
                        return None

                current_duration = duration_days(existing.get("period_start"), existing.get("period_end"))
                new_duration = duration_days(period_start, period_end)
                choose_new = False
                if current_duration is None and new_duration is not None:
                    choose_new = True
                elif current_duration is not None and new_duration is not None and new_duration < current_duration:
                    choose_new = True
                elif current_value is None or abs(numeric_value) < abs(float(current_value)):
                    choose_new = True

                if choose_new:
                    existing.update(
                        {
                            "value": numeric_value,
                            "accession": accession if accession else existing.get("accession"),
                            "period_start": period_start or existing.get("period_start"),
                            "source_fact_id": source_id if source_id is not None else existing.get("source_fact_id"),
                        }
                    )
            else:
                # For income statement and balance sheet, keep the larger magnitude (default behavior).
                if current_value is None or abs(numeric_value) > abs(float(current_value)):
                    existing["value"] = numeric_value
                    if accession and not existing.get("accession"):
                        existing["accession"] = accession
                    existing["source_fact_id"] = source_id if source_id is not None else existing.get("source_fact_id")
    return [aggregated[k] for k in sorted(aggregated.keys(), key=lambda x: (x[2], x[4], x[5]))]


def log_tie_checks(aggregated: List[Dict[str, Any]]) -> None:
    """Log tie deltas per period to aid debugging; optionally raise on violations."""
    by_period: Dict[Any, Dict[str, Dict[str, Any]]] = {}
    for row in aggregated:
        period = row.get("period_end")
        stmt = row.get("statement")
        if not period or not stmt:
            continue
        by_period.setdefault(period, {}).setdefault(stmt, {})[row.get("line_item")] = row.get("value")
    violations: List[str] = []
    for period, stmts in by_period.items():
        bs = stmts.get("balance_sheet", {})
        cf = stmts.get("cash_flow", {})
        assets = bs.get("assets")
        liabilities = bs.get("liabilities")
        equity = bs.get("equity")
        if assets is not None and liabilities is not None and equity is not None:
            delta = assets - (liabilities + equity)
            if abs(delta) > TIE_TOLERANCE:
                msg = f"Balance sheet tie off for {period}: {delta}"
                logger.warning(msg)
                violations.append(msg)
        cfo = cf.get("cfo")
        cfi = cf.get("cfi")
        cff = cf.get("cff")
        if cfo is not None and cfi is not None and cff is not None:
            cf_sum = cfo + cfi + cff
            # cash delta check occurs in summary; here we only log sum magnitude.
            if abs(cf_sum) > TIE_TOLERANCE:
                msg = f"Cash flow sum off for {period}: {cf_sum}"
                logger.warning(msg)
                violations.append(msg)
    if HARD_FAIL_TIES and violations:
        raise ValueError(f"Tie violations detected: {'; '.join(violations)}")


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
                SELECT id, ticker, cik, accession, period_start, period_end, period_type, statement, line_item, value, unit
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
            log_tie_checks(aggregated or [])
        conn.commit()
    return inserted
