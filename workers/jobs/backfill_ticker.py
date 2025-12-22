import logging
from typing import Optional

from .fetch_filings import fetch_missing_filings
from .materialize_canonical import run_materialization
from .parse_filing import parse_filing

logger = logging.getLogger(__name__)


def backfill_ticker(ticker: str, limit: int = 24, storage_root: Optional[str] = None) -> dict:
    """
    Fetch and parse missing recent filings (default 24) for a ticker, then materialize canonical facts.
    Use when expanding historical coverage beyond the default pipeline depth.
    """
    fetch_result = fetch_missing_filings(ticker, limit=limit, storage_root=storage_root)
    saved = fetch_result.get("saved", [])
    parsed = []
    for entry in saved:
        accession = entry["accession"]
        cik = fetch_result.get("cik")
        path = entry.get("primary_path") or entry.get("path")
        if not path:
            continue
        parsed.append(parse_filing(accession, cik, ticker, path))
    inserted = run_materialization(ticker)
    dropped_total = sum(item.get("dropped", 0) for item in parsed)
    result = {
        "ticker": ticker.upper(),
        "fetched": saved,
        "parsed": parsed,
        "canonical_inserted": inserted.get("inserted", inserted),
        "dropped_facts": dropped_total,
        "existing_count": fetch_result.get("existing_count"),
    }
    logger.info("Backfill complete for %s (limit=%d): %s", ticker, limit, result)
    return result
