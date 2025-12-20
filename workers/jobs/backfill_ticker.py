import logging
from typing import Optional

from .run_pipeline import run_pipeline

logger = logging.getLogger(__name__)


def backfill_ticker(ticker: str, limit: int = 8, storage_root: Optional[str] = None) -> dict:
    """
    Fetch and parse multiple recent filings (default 8) for a ticker, then materialize canonical facts.
    Use when expanding historical coverage beyond the default pipeline depth.
    """
    result = run_pipeline(ticker, limit=limit, storage_root=storage_root)
    logger.info("Backfill complete for %s (limit=%d): %s", ticker, limit, result)
    return result
