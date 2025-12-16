import logging
from typing import Dict

from ..statements import build_statements

logger = logging.getLogger(__name__)


def build_for_ticker(ticker: str, max_periods: int = 8) -> Dict[str, object]:
    data = build_statements(ticker, max_periods=max_periods)
    logger.info("Built statements for %s with %d periods", ticker, len(data.get("periods", [])))
    return {"ticker": ticker.upper(), **data}
