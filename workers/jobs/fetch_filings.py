import logging
from typing import Any, Dict, List, Optional

from ..db import upsert_filing
from ..edgar_client import EDGARClient, StorageWriter
from ..ticker_map import get_cik_for_ticker, get_coverage_status

logger = logging.getLogger(__name__)


def _select_recent_accessions(submissions: Dict[str, Any], limit: int) -> List[str]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    selected: List[str] = []
    for form, acc in zip(forms, accessions):
        if form in {"10-K", "10-Q"}:
            selected.append(acc)
        if len(selected) >= limit:
            break
    return selected


def fetch_latest_filings(ticker: str, limit: int = 3, storage_root: Optional[str] = None) -> Dict[str, Any]:
    """Fetch recent filings for a ticker and persist to storage/raw."""
    cik = get_cik_for_ticker(ticker)
    if not cik:
        raise ValueError(f"Ticker {ticker} not found in SEC ticker lists")

    client = EDGARClient()
    writer = StorageWriter(storage_root)

    submissions = client.get_submissions(cik)
    meta_path = writer.save_json(cik, "submissions", submissions)

    saved = []
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])

    for form, accession, filed_at in zip(forms, accessions, filing_dates):
        if form not in {"10-K", "10-Q"}:
            continue
        if len(saved) >= limit:
            break
        index_content = client.get_filing_index(cik, accession)
        index_path = writer.save_bytes(cik, accession.replace("-", ""), index_content, suffix="index.html")
        primary_content = client.resolve_primary_html(cik, accession, index_content) or index_content
        primary_path = writer.save_bytes(
            cik, f"{accession.replace('-', '')}_primary", primary_content, suffix="html"
        )
        saved.append(
            {
                "accession": accession,
                "form": form,
                "filed_at": filed_at,
                "primary_path": primary_path,
                "index_path": index_path,
            }
        )
        upsert_filing(
            ticker=ticker,
            cik=cik,
            accession=accession,
            form=form,
            filed_at=filed_at,
            path=primary_path,
            submissions_path=meta_path,
        )
        logger.info("Saved filing %s (%s) for %s to %s", accession, form, ticker, primary_path)

    return {
        "ticker": ticker.upper(),
        "cik": cik,
        "covered": get_coverage_status(ticker),
        "saved": saved,
        "submissions_path": meta_path,
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Fetch latest EDGAR filings for a ticker.")
    parser.add_argument("ticker", help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--limit", type=int, default=3, help="Number of filings to fetch")
    parser.add_argument("--storage-root", default=None, help="Override storage root directory")
    args = parser.parse_args()

    try:
        result = fetch_latest_filings(args.ticker, limit=args.limit, storage_root=args.storage_root)
        print(json.dumps(result, indent=2))
    except Exception as exc:  # pragma: no cover - CLI usage
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
