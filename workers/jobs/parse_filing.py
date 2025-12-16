import logging
from typing import Dict

from ..edgar_client import EDGARClient, StorageWriter
from ..parser import parse_and_store

logger = logging.getLogger(__name__)


def parse_filing(accession: str, cik: str, ticker: str, html_path: str) -> Dict[str, int]:
    logger.info("Parsing filing %s for %s from %s", accession, ticker, html_path)
    result = parse_and_store(accession, cik, ticker, html_path)
    if result.get("inserted", 0) > 0:
        return result

    # Fallback: re-fetch primary HTML if the saved file was an index or unparsable.
    client = EDGARClient()
    writer = StorageWriter()
    index_content = client.get_filing_index(cik, accession)
    primary_content = client.resolve_primary_html(cik, accession, index_content) or index_content
    fallback_path = writer.save_bytes(cik, f"{accession.replace('-', '')}_primary_refetched", primary_content, "html")
    logger.info("Fallback fetch for %s saved to %s", accession, fallback_path)
    return parse_and_store(accession, cik, ticker, fallback_path)
