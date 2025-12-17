import csv
import json
import os
from typing import Dict, Optional, Tuple

DEFAULT_PATHS = (
    os.getenv("TICKER_CIK_PATH"),
    os.path.join(os.getcwd(), "data", "ticker_cik.csv"),
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "ticker_cik.csv"),
    "/data/ticker_cik.csv",
)

SEC_TICKER_PATHS = (
    os.getenv("SEC_TICKER_JSON"),
    os.path.join(os.getcwd(), "data", "company_tickers.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "company_tickers.json"),
    "/data/company_tickers.json",
)

# Cache the last seen map and mtime so edits to the CSV are picked up without restarts.
_CACHE: Tuple[Dict[str, str], Optional[float]] = ({}, None)
_SEC_CACHE: Tuple[Dict[str, str], Optional[float]] = ({}, None)


def _load_map() -> Dict[str, str]:
    global _CACHE
    for path in DEFAULT_PATHS:
        if not path or not os.path.isfile(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        cached_map, cached_mtime = _CACHE
        if cached_map and mtime is not None and mtime == cached_mtime:
            return cached_map

        mapping: Dict[str, str] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row["ticker"].strip().upper()
                cik = row["cik"].strip()
                mapping[ticker] = cik
        if mapping:
            _CACHE = (mapping, mtime)
            return mapping
    return _CACHE[0]


def _load_sec_map() -> Dict[str, str]:
    """Load the full SEC ticker → CIK dataset if present."""
    global _SEC_CACHE
    for path in SEC_TICKER_PATHS:
        if not path or not os.path.isfile(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None

        cached_map, cached_mtime = _SEC_CACHE
        if cached_map and mtime is not None and mtime == cached_mtime:
            return cached_map

        with open(path) as f:
            data = json.load(f)

        mapping: Dict[str, str] = {}
        for entry in data.values():
            ticker = entry.get("ticker")
            cik = entry.get("cik_str") or entry.get("cik")
            if not ticker or cik is None:
                continue
            mapping[ticker.strip().upper()] = f"{int(cik):010d}"

        if mapping:
            _SEC_CACHE = (mapping, mtime)
            return mapping
    return _SEC_CACHE[0]


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    t = ticker.strip().upper()
    mapping = _load_map()
    if t in mapping:
        return mapping[t]
    return _load_sec_map().get(t)


def get_coverage_status(ticker: str) -> bool:
    """Return True if the ticker is in our curated IR coverage list."""
    if not ticker:
        return False
    return ticker.strip().upper() in _load_map()


def list_supported_tickers() -> Dict[str, str]:
    return _load_map()
