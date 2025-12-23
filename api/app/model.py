from typing import Any, Dict, List, Optional, Set

try:
    from .summary_utils import ALLOWED_STATEMENTS, LINE_ITEM_TO_STATEMENTS, build_forecast_summary
except ImportError:  # pragma: no cover - fallback for direct module imports in tests
    from summary_utils import ALLOWED_STATEMENTS, LINE_ITEM_TO_STATEMENTS, build_forecast_summary

MODEL_LINE_ITEM_TO_STATEMENTS: Dict[str, Set[str]] = {
    **LINE_ITEM_TO_STATEMENTS,
    "fcf": {"cash_flow"},
}


def _group_by_statement(
    values: Dict[str, Dict[str, Optional[float]]],
    sources: Optional[Dict[str, Dict[str, Any]]] = None,
    default_source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {stmt: {} for stmt in ALLOWED_STATEMENTS}
    for line_item, payload in values.items():
        statements = MODEL_LINE_ITEM_TO_STATEMENTS.get(line_item, set())
        source_payload = sources.get(line_item) if sources else None
        if source_payload is None and default_source:
            source_payload = default_source
        for stmt in statements:
            payload_entry = dict(payload)
            if source_payload:
                payload_entry["source"] = source_payload
            grouped.setdefault(stmt, {})[line_item] = payload_entry
    return grouped


def get_model(ticker: str, actuals_limit: int = 4) -> Dict[str, Any]:
    try:
        from .summary import get_summary
    except ImportError:  # pragma: no cover - fallback for direct module imports in tests
        from summary import get_summary

    summary = get_summary(ticker)
    periods: List[Dict[str, Any]] = summary.get("periods", [])
    drivers = summary.get("drivers", {}) or {}
    forecast = summary.get("forecast", []) or []

    statements: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        stmt: {"actuals": [], "forecast": []} for stmt in ALLOWED_STATEMENTS
    }

    for period in periods[:actuals_limit]:
        grouped = _group_by_statement(period.get("values", {}), sources=period.get("sources", {}))
        for stmt, values in grouped.items():
            statements[stmt]["actuals"].append(
                {
                    "period_end": period.get("period_end"),
                    "values": values,
                }
            )

    for entry in forecast:
        grouped = _group_by_statement(entry.get("values", {}))
        for stmt, values in grouped.items():
            statements[stmt]["forecast"].append(
                {
                    "period_end": entry.get("period_end"),
                    "values": values,
                    "scenario": entry.get("scenario"),
                    "period_index": entry.get("period_index"),
                    "assumptions": entry.get("assumptions"),
                }
            )

    for stmt, payload in statements.items():
        payload["actuals"] = sorted(
            payload["actuals"],
            key=lambda item: item.get("period_end") or "",
        )
        payload["forecast"] = sorted(
            payload["forecast"],
            key=lambda item: (item.get("scenario") or "", item.get("period_index") or 0),
        )

    scenarios = sorted({entry.get("scenario") for entry in forecast if entry.get("scenario")})
    as_of = periods[0].get("period_end") if periods else None
    return {
        "ticker": summary.get("ticker"),
        "as_of": as_of,
        "drivers": drivers,
        "scenarios": scenarios,
        "statements": statements,
        "forecast_summary": build_forecast_summary(forecast),
    }
