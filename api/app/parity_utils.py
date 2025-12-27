from typing import Any, Dict, Iterable, List, Tuple


def statement_counts(statement_period: Dict[str, Any]) -> Tuple[Dict[str, int], int]:
    lines = statement_period.get("lines") or {}
    counts = {stmt: len(items or []) for stmt, items in lines.items()}
    return counts, sum(counts.values())


def coverage_mismatches(
    summary_period: Dict[str, Any],
    coverage: Dict[str, Any],
    statement_period: Dict[str, Any],
) -> List[str]:
    mismatches: List[str] = []
    if not summary_period or not statement_period:
        return ["missing periods"]

    summary_end = summary_period.get("period_end")
    statement_end = statement_period.get("period_end")
    if summary_end and statement_end and summary_end != statement_end:
        return [f"period mismatch summary={summary_end} statements={statement_end}"]

    counts, total = statement_counts(statement_period)
    total_found = coverage.get("total_found")
    if total_found is not None and total != total_found:
        mismatches.append(f"total mismatch summary={total_found} statements={total}")

    for stmt, stats in (coverage.get("by_statement") or {}).items():
        found = stats.get("found")
        if found is not None and counts.get(stmt, 0) != found:
            mismatches.append(
                f"{stmt} mismatch summary={found} statements={counts.get(stmt, 0)}"
            )

    return mismatches


def period_start_consistent(
    values: Dict[str, Any], line_items: Iterable[str]
) -> Tuple[bool, Dict[str, Any]]:
    starts = {item: values.get(item, {}).get("start") for item in line_items}
    unique = {value for value in starts.values() if value}
    return len(unique) <= 1, starts
