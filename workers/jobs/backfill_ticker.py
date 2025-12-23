import logging
from typing import Optional

from .fetch_filings import fetch_missing_filings
from .materialize_canonical import run_materialization
from .parse_filing import parse_filing
from ..db import list_filings_by_ticker

logger = logging.getLogger(__name__)


def backfill_ticker(ticker: str, limit: int = 24, storage_root: Optional[str] = None) -> dict:
    """
    Fetch and parse missing recent filings (default 24) for a ticker, then materialize canonical facts.
    Use when expanding historical coverage beyond the default pipeline depth.
    """
    fetch_result = fetch_missing_filings(ticker, limit=limit, storage_root=storage_root)
    saved = fetch_result.get("saved", [])
    parsed = []
    parsed_accessions = set()
    for entry in saved:
        accession = entry["accession"]
        cik = fetch_result.get("cik")
        path = entry.get("primary_path") or entry.get("path")
        if not path:
            continue
        parsed.append(parse_filing(accession, cik, ticker, path))
        parsed_accessions.add(accession)

    if len(parsed) < limit:
        existing_filings = list_filings_by_ticker(ticker, limit=limit)
        for filing in existing_filings:
            accession = filing.get("accession")
            if not accession or accession in parsed_accessions:
                continue
            cik = filing.get("cik") or fetch_result.get("cik")
            path = filing.get("path")
            if not path:
                continue
            parsed.append(parse_filing(accession, cik, ticker, path))
            parsed_accessions.add(accession)
            if len(parsed) >= limit:
                break
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
