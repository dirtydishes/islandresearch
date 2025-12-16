import logging

from ..canonical import materialize_canonical_for_ticker

logger = logging.getLogger(__name__)


def run_materialization(ticker: str) -> dict:
    inserted = materialize_canonical_for_ticker(ticker)
    logger.info("Canonical facts inserted for %s: %d", ticker, inserted)
    return {"ticker": ticker.upper(), "inserted": inserted}
