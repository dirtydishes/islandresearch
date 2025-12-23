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
RESIDUAL_TOLERANCE = _env_float("RESIDUAL_TOLERANCE", 1e-2)

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
    cleaned = unit.strip().upper()
    if cleaned in {"USD/SHARES", "USD/SHARE", "USD PER SHARE"}:
        return "USDPERSHARE"
    return cleaned


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
    def duration_days(start, end) -> Optional[int]:
        if start is None or end is None:
            return None
        try:
            return (end - start).days
        except Exception:
            return None

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
            if statement in ("cash_flow", "income_statement"):
                # Prefer the shortest duration (closest start to end) when period_start present.
                current_duration = duration_days(existing.get("period_start"), existing.get("period_end"))
                new_duration = duration_days(period_start, period_end)
                choose_new = False
                if current_duration is None and new_duration is not None:
                    choose_new = True
                elif current_duration is not None and new_duration is not None and new_duration < current_duration:
                    choose_new = True
                else:
                    if statement == "cash_flow":
                        if current_value is None or abs(numeric_value) < abs(float(current_value)):
                            choose_new = True
                    else:
                        if current_value is None or abs(numeric_value) > abs(float(current_value)):
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


def _add_balance_sheet_residuals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add residual balance sheet line items when totals exist but components are missing.
    """
    by_period = {}
    for row in rows:
        if row.get("statement") != "balance_sheet":
            continue
        period = row.get("period_end")
        if period is None:
            continue
        by_period.setdefault(period, []).append(row)

    derived = []

    def _residual(total_item: str, component_items: list[str], derived_item: str, period_rows: list[Dict[str, Any]]) -> None:
        line_map = {r.get("line_item"): r for r in period_rows}
        if derived_item in line_map:
            return
        total_row = line_map.get(total_item)
        if not total_row:
            return
        total_val = total_row.get("value")
        unit = total_row.get("unit")
        if total_val is None:
            return
        subtotal = 0.0
        for item in component_items:
            row = line_map.get(item)
            if not row:
                continue
            if unit and row.get("unit") and row.get("unit") != unit:
                continue
            val = row.get("value")
            if val is None:
                continue
            subtotal += float(val)
        residual = float(total_val) - subtotal
        if abs(residual) <= RESIDUAL_TOLERANCE:
            return
        derived.append(
            {
                "ticker": total_row.get("ticker"),
                "cik": total_row.get("cik"),
                "accession": total_row.get("accession"),
                "period_start": total_row.get("period_start"),
                "period_end": total_row.get("period_end"),
                "period_type": total_row.get("period_type"),
                "statement": "balance_sheet",
                "line_item": derived_item,
                "value": residual,
                "unit": unit,
                "source_fact_id": None,
            }
        )

    for period, period_rows in by_period.items():
        _residual(
            "assets_current",
            ["cash", "short_term_investments", "accounts_receivable", "inventory", "prepaid_expenses"],
            "other_assets_current",
            period_rows,
        )
        _residual(
            "assets_noncurrent",
            ["ppe", "goodwill", "intangible_assets"],
            "other_assets_noncurrent",
            period_rows,
        )
        _residual(
            "liabilities_current",
            ["accounts_payable", "accrued_expenses", "deferred_revenue_current", "debt_current"],
            "other_liabilities_current",
            period_rows,
        )
        _residual(
            "liabilities_noncurrent",
            ["deferred_revenue_noncurrent", "debt_long_term", "minority_interest"],
            "other_liabilities_noncurrent",
            period_rows,
        )

    if not derived:
        return rows
    combined = rows + derived
    return sorted(combined, key=lambda x: (x.get("period_end"), x.get("statement"), x.get("line_item")))


def _add_income_statement_derivations(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add derived income statement line items when component facts are present.
    """
    by_period: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        period = row.get("period_end")
        if period is None:
            continue
        by_period.setdefault(period, []).append(row)

    derived: List[Dict[str, Any]] = []

    def _append_row(template: Dict[str, Any], line_item: str, value: float) -> Dict[str, Any]:
        row = {
            "ticker": template.get("ticker"),
            "cik": template.get("cik"),
            "accession": template.get("accession"),
            "period_start": template.get("period_start"),
            "period_end": template.get("period_end"),
            "period_type": template.get("period_type"),
            "statement": "income_statement",
            "line_item": line_item,
            "value": value,
            "unit": template.get("unit"),
            "source_fact_id": None,
        }
        derived.append(row)
        return row

    for period_rows in by_period.values():
        line_map = {r.get("line_item"): r for r in period_rows if r.get("statement") == "income_statement"}
        cash_map = {r.get("line_item"): r for r in period_rows if r.get("statement") == "cash_flow"}

        def _value(row: Optional[Dict[str, Any]], unit: Optional[str]) -> Optional[float]:
            if not row:
                return None
            if unit and row.get("unit") and row.get("unit") != unit:
                return None
            val = row.get("value")
            return float(val) if val is not None else None

        revenue = line_map.get("revenue")
        gross_profit = line_map.get("gross_profit")
        operating_expenses = line_map.get("operating_expenses")

        if "cogs" not in line_map and revenue and gross_profit and revenue.get("unit") == gross_profit.get("unit"):
            rev_val = _value(revenue, revenue.get("unit"))
            gp_val = _value(gross_profit, revenue.get("unit"))
            if rev_val is not None and gp_val is not None:
                cogs_row = _append_row(revenue, "cogs", rev_val - gp_val)
                line_map["cogs"] = cogs_row

        if "total_expenses" not in line_map and operating_expenses:
            unit = operating_expenses.get("unit")
            op_val = _value(operating_expenses, unit)
            cogs_val = _value(line_map.get("cogs"), unit)
            if op_val is not None and cogs_val is not None:
                _append_row(operating_expenses, "total_expenses", op_val + cogs_val)

        if "ebitda" not in line_map:
            operating_income = line_map.get("operating_income")
            depreciation = cash_map.get("depreciation_amortization")
            if operating_income and depreciation and operating_income.get("unit") == depreciation.get("unit"):
                op_val = _value(operating_income, operating_income.get("unit"))
                dep_val = _value(depreciation, operating_income.get("unit"))
                if op_val is not None and dep_val is not None:
                    _append_row(operating_income, "ebitda", op_val + dep_val)

    if not derived:
        return rows
    combined = rows + derived
    return sorted(combined, key=lambda x: (x.get("period_end"), x.get("statement"), x.get("line_item")))


def _add_cash_flow_residuals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add derived cash flow line items from statement totals when missing.
    """
    by_period: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        if row.get("statement") != "cash_flow":
            continue
        period = row.get("period_end")
        if period is None:
            continue
        by_period.setdefault(period, []).append(row)

    derived: List[Dict[str, Any]] = []

    for period_rows in by_period.values():
        line_map = {r.get("line_item"): r for r in period_rows}
        template = line_map.get("cfo") or line_map.get("cfi") or line_map.get("cff") or line_map.get("change_in_cash")
        if not template:
            continue
        base_unit = template.get("unit")

        def _value(item: str) -> Optional[float]:
            row = line_map.get(item)
            if not row:
                return None
            if base_unit and row.get("unit") and row.get("unit") != base_unit:
                return None
            val = row.get("value")
            return float(val) if val is not None else None

        def _append(line_item: str, value: float) -> None:
            row = {
                "ticker": template.get("ticker"),
                "cik": template.get("cik"),
                "accession": template.get("accession"),
                "period_start": template.get("period_start"),
                "period_end": template.get("period_end"),
                "period_type": template.get("period_type"),
                "statement": "cash_flow",
                "line_item": line_item,
                "value": value,
                "unit": base_unit,
                "source_fact_id": None,
            }
            derived.append(row)
            line_map[line_item] = row

        cfo = _value("cfo")
        cfi = _value("cfi")
        cff = _value("cff")

        if "change_in_cash" not in line_map and None not in (cfo, cfi, cff):
            total = float(cfo + cfi + cff)
            fx = _value("fx_on_cash")
            if fx is not None:
                total += fx
            restricted = _value("change_in_restricted_cash")
            if restricted is not None:
                total += restricted
            _append("change_in_cash", total)

        if "fx_on_cash" not in line_map:
            change_in_cash = _value("change_in_cash")
            if None not in (change_in_cash, cfo, cfi, cff):
                fx_val = float(change_in_cash - (cfo + cfi + cff))
                restricted = _value("change_in_restricted_cash")
                if restricted is not None:
                    fx_val -= restricted
                _append("fx_on_cash", fx_val)

        if "change_in_restricted_cash" not in line_map:
            change_in_cash = _value("change_in_cash")
            fx_on_cash = _value("fx_on_cash")
            if None not in (change_in_cash, cfo, cfi, cff, fx_on_cash):
                restricted_val = float(change_in_cash - (cfo + cfi + cff + fx_on_cash))
                _append("change_in_restricted_cash", restricted_val)

    if not derived:
        return rows
    combined = rows + derived
    return sorted(combined, key=lambda x: (x.get("period_end"), x.get("statement"), x.get("line_item")))


def _collect_tie_violations(aggregated: List[Dict[str, Any]], tolerance: Optional[float] = None) -> List[str]:
    by_period: Dict[Any, Dict[str, Dict[str, Any]]] = {}
    for row in aggregated:
        period = row.get("period_end")
        stmt = row.get("statement")
        if not period or not stmt:
            continue
        by_period.setdefault(period, {}).setdefault(stmt, {})[row.get("line_item")] = row.get("value")

    tol = TIE_TOLERANCE if tolerance is None else tolerance
    violations: List[str] = []
    for period, stmts in by_period.items():
        bs = stmts.get("balance_sheet", {})
        assets = bs.get("assets")
        liabilities = bs.get("liabilities")
        equity = bs.get("equity")
        if assets is not None and liabilities is not None and equity is not None:
            delta = assets - (liabilities + equity)
            if abs(delta) > tol:
                violations.append(f"Balance sheet tie off for {period}: {delta}")

        cf = stmts.get("cash_flow", {})
        cfo = cf.get("cfo")
        cfi = cf.get("cfi")
        cff = cf.get("cff")
        change_in_cash = cf.get("change_in_cash")
        fx_on_cash = cf.get("fx_on_cash") or 0
        restricted = cf.get("change_in_restricted_cash") or 0
        if None not in (cfo, cfi, cff, change_in_cash):
            delta = (cfo + cfi + cff + fx_on_cash + restricted) - change_in_cash
            if abs(delta) > tol:
                violations.append(f"Cash flow tie off for {period}: {delta}")

    return violations


def log_tie_checks(aggregated: List[Dict[str, Any]], strict: Optional[bool] = None) -> List[str]:
    """Log tie deltas per period to aid debugging; optionally raise on violations."""
    violations = _collect_tie_violations(aggregated)
    for msg in violations:
        logger.warning(msg)
    enforce = HARD_FAIL_TIES if strict is None else strict
    if enforce and violations:
        raise ValueError(f"Tie violations detected: {'; '.join(violations)}")
    return violations


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
          SELECT MAX(filed_at) AS period_end
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
    if isinstance(row, dict):
        return row.get("period_end")
    return row[0]


def materialize_canonical_for_ticker(ticker: str, strict_ties: Optional[bool] = None) -> int:
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
                aggregated = _add_balance_sheet_residuals(aggregated)
                aggregated = _add_income_statement_derivations(aggregated)
                aggregated = _add_cash_flow_residuals(aggregated)
                insert_sql = """
                INSERT INTO canonical_facts (ticker, cik, accession, period_start, period_end, period_type, statement, line_item, value, unit, source_fact_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = [
                    (
                        row["ticker"],
                        row.get("cik"),
                        row.get("accession"),
                        row.get("period_start"),
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
            log_tie_checks(aggregated or [], strict=strict_ties)
        conn.commit()
    return inserted
