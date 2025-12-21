import logging
from typing import Optional

from .fetch_filings import fetch_latest_filings
from .parse_filing import parse_filing
from .materialize_canonical import run_materialization

logger = logging.getLogger(__name__)


def run_pipeline(ticker: str, limit: int = 12, storage_root: Optional[str] = None) -> dict:
    """
    End-to-end helper: fetch filings, parse saved filings (default last 12), then materialize canonical facts.
    """
    fetch_result = fetch_latest_filings(ticker, limit=limit, storage_root=storage_root)
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
    return {
        "ticker": ticker.upper(),
        "fetched": saved,
        "parsed": parsed,
        "canonical_inserted": inserted.get("inserted", inserted),
        "dropped_facts": dropped_total,
    }
