import argparse
import logging
from typing import Any, Dict, List, Optional

from .fetch_filings import fetch_missing_filings
from .materialize_canonical import run_materialization
from .parse_filing import parse_filing
from ..ticker_map import list_supported_tickers

logger = logging.getLogger(__name__)


def backfill_recent(
    limit: int = 4,
    tickers: Optional[List[str]] = None,
    storage_root: Optional[str] = None,
    strict_ties: bool = False,
) -> Dict[str, Any]:
    """
    Fetch and parse only newly missing filings for each ticker, then materialize canonical facts.
    Intended for lightweight, scheduled refreshes without reprocessing existing filings.
    """
    if tickers:
        selected = [t.strip().upper() for t in tickers if t.strip()]
    else:
        selected = sorted(list_supported_tickers().keys())

    results = []
    failures = 0
    for ticker in selected:
        try:
            fetch_result = fetch_missing_filings(ticker, limit=limit, storage_root=storage_root)
            saved = fetch_result.get("saved", [])
            parsed = []
            parsed_accessions = set()
            for entry in saved:
                accession = entry.get("accession")
                if not accession or accession in parsed_accessions:
                    continue
                cik = fetch_result.get("cik")
                path = entry.get("primary_path") or entry.get("path")
                if not path or not cik:
                    continue
                parsed.append(parse_filing(accession, cik, ticker, path))
                parsed_accessions.add(accession)
            inserted = 0
            if saved:
                inserted = run_materialization(ticker, strict_ties=strict_ties).get("inserted", 0)
            else:
                logger.info("No new filings for %s; skipping materialization.", ticker)
            dropped_total = sum(item.get("dropped", 0) for item in parsed)
            results.append(
                {
                    "ticker": ticker.upper(),
                    "fetched": saved,
                    "parsed": parsed,
                    "canonical_inserted": inserted,
                    "dropped_facts": dropped_total,
                    "existing_count": fetch_result.get("existing_count"),
                }
            )
        except Exception as exc:  # pragma: no cover - guarded by runtime logs
            logger.exception("Recent backfill failed for %s: %s", ticker, exc)
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
    parser = argparse.ArgumentParser(description="Backfill newly missing filings for covered tickers.")
    parser.add_argument("--limit", type=int, default=4, help="Number of new filings per ticker to fetch.")
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
    result = backfill_recent(limit=args.limit, tickers=tickers, strict_ties=args.strict_ties)
    logger.info(
        "Recent backfill complete: %d success, %d failed (limit=%d)",
        result.get("success"),
        result.get("failed"),
        result.get("limit"),
    )


if __name__ == "__main__":
    _main()
