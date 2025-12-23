import logging

from ..canonical import materialize_canonical_for_ticker

logger = logging.getLogger(__name__)


def run_materialization(ticker: str, strict_ties: bool = True) -> dict:
    inserted = materialize_canonical_for_ticker(ticker, strict_ties=strict_ties)
    logger.info("Canonical facts inserted for %s: %d", ticker, inserted)
    return {"ticker": ticker.upper(), "inserted": inserted}
