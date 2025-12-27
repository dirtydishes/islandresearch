import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.parity_utils import coverage_mismatches, period_start_consistent, statement_counts
from app.summary import get_summary
from app.statements import get_statements_for_ticker
from app.ticker_map import list_supported_tickers


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check summary/statement parity for sample tickers.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker list.")
    parser.add_argument("--max-tickers", type=int, default=10, help="Max tickers when using curated list.")
    parser.add_argument("--limit", type=int, default=8, help="Statement periods to fetch.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        tickers = sorted(list_supported_tickers().keys())[: args.max_tickers]

    issues = []
    for ticker in tickers:
        summary = get_summary(ticker)
        periods = summary.get("periods", [])
        if not periods:
            issues.append((ticker, ["no summary periods"]))
            continue
        latest_summary = periods[0]
        period_end = latest_summary.get("period_end")
        coverage = summary.get("coverage", {}).get(period_end, {}) if period_end else {}

        statements = get_statements_for_ticker(ticker, limit=args.limit)
        statement_periods = statements.get("periods", [])
        if not statement_periods:
            issues.append((ticker, ["no statements"]))
            continue
        latest_statement = statement_periods[0]

        mismatches = coverage_mismatches(latest_summary, coverage, latest_statement)
        values = latest_summary.get("values", {})
        consistent, starts = period_start_consistent(values, ("revenue", "net_income", "cfo"))
        if not consistent:
            mismatches.append(f"period_start mismatch {starts}")

        counts, total = statement_counts(latest_statement)
        if mismatches:
            issues.append((ticker, mismatches))
        else:
            print(f"{ticker}: period={period_end} coverage={total}/{coverage.get('total_expected')} counts={counts}")

    if issues:
        print("mismatches:")
        for ticker, errors in issues:
            print(f"{ticker}: {', '.join(errors)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
