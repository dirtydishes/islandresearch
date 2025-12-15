import logging
from typing import Dict

from ..parser import parse_and_store

logger = logging.getLogger(__name__)


def parse_filing(accession: str, cik: str, ticker: str, html_path: str) -> Dict[str, int]:
    logger.info("Parsing filing %s for %s from %s", accession, ticker, html_path)
    return parse_and_store(accession, cik, ticker, html_path)
