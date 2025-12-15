import csv
import os
from functools import lru_cache
from typing import Dict, Optional

DEFAULT_PATHS = (
    os.getenv("TICKER_CIK_PATH"),
    os.path.join(os.getcwd(), "data", "ticker_cik.csv"),
    "/data/ticker_cik.csv",
)


@lru_cache(maxsize=1)
def _load_map() -> Dict[str, str]:
    for path in DEFAULT_PATHS:
        if not path:
            continue
        if os.path.isfile(path):
            mapping: Dict[str, str] = {}
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = row["ticker"].strip().upper()
                    cik = row["cik"].strip()
                    mapping[ticker] = cik
            if mapping:
                return mapping
    return {}


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    return _load_map().get(ticker.strip().upper())


def list_supported_tickers() -> Dict[str, str]:
    return _load_map()
