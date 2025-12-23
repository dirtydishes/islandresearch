import argparse
import logging
from typing import Any, Dict, List, Optional

from .backfill_ticker import backfill_ticker
from ..ticker_map import list_supported_tickers

logger = logging.getLogger(__name__)


def backfill_all(
    limit: int = 8,
    max_tickers: Optional[int] = None,
    tickers: Optional[List[str]] = None,
    storage_root: Optional[str] = None,
    strict_ties: bool = True,
) -> Dict[str, Any]:
    if tickers:
        selected = [t.strip().upper() for t in tickers if t.strip()]
    else:
        selected = sorted(list_supported_tickers().keys())

    if max_tickers is not None:
        selected = selected[: max_tickers]

    results = []
    failures = 0
    for ticker in selected:
        try:
            result = backfill_ticker(
                ticker, limit=limit, storage_root=storage_root, strict_ties=strict_ties
            )
            results.append(result)
        except Exception as exc:  # pragma: no cover - guarded by runtime logs
            logger.exception("Backfill failed for %s: %s", ticker, exc)
            failures += 1
            results.append({"ticker": ticker, "error": str(exc)})

    return {
        "tickers": selected,
        "limit": limit,
        "success": len(selected) - failures,
        "failed": failures,
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill filings for all covered tickers.")
    parser.add_argument("--limit", type=int, default=8, help="Number of filings per ticker to backfill.")
    parser.add_argument("--max-tickers", type=int, default=None, help="Optional cap on tickers processed.")
    parser.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated tickers to backfill (overrides curated list).",
    )
    parser.add_argument(
        "--strict-ties",
        action="store_true",
        default=False,
        help="Fail backfill if tie checks do not pass.",
    )
    return parser.parse_args()


def _main() -> None:
    args = _parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None
    result = backfill_all(
        limit=args.limit,
        max_tickers=args.max_tickers,
        tickers=tickers,
        strict_ties=args.strict_ties,
    )
    logger.info(
        "Backfill complete: %d success, %d failed (limit=%d)",
        result.get("success"),
        result.get("failed"),
        result.get("limit"),
    )


if __name__ == "__main__":
    _main()
