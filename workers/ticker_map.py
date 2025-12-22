import csv
import json
import os
from typing import Dict, Optional, Tuple

DEFAULT_PATHS = (
    os.getenv("TICKER_CIK_PATH"),
    os.path.join(os.getcwd(), "data", "ticker_cik.csv"),
    os.path.join(os.path.dirname(__file__), "..", "data", "ticker_cik.csv"),
    "/data/ticker_cik.csv",
)

SEC_TICKER_PATHS = (
    os.getenv("SEC_TICKER_JSON"),
    os.path.join(os.getcwd(), "data", "company_tickers.json"),
    os.path.join(os.path.dirname(__file__), "..", "data", "company_tickers.json"),
    "/data/company_tickers.json",
)
SEC_DOWNLOAD_TARGETS = (
    os.getenv("SEC_TICKER_JSON"),
    os.path.join(os.getcwd(), "data", "company_tickers.json"),
    os.path.join(os.path.dirname(__file__), "..", "data", "company_tickers.json"),
    "/data/company_tickers.json",
)

_CACHE: Tuple[Dict[str, str], Optional[float]] = ({}, None)
_SEC_CACHE: Tuple[Dict[str, str], Optional[float]] = ({}, None)


def _download_sec_tickers(target_path: str) -> Optional[Dict[str, str]]:
    """
    Fetch the SEC company_tickers.json when it is missing (common when the data/ volume
    is not mounted into the container) and persist it for subsequent runs.
    """
    try:
        import requests
    except ImportError:
        return None

    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": os.getenv("EDGAR_USER_AGENT", "deltaisland-research/0.1 (contact@deltaisland.local)")},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w") as f:
            json.dump(data, f)
        mapping: Dict[str, str] = {}
        for entry in data.values():
            ticker = entry.get("ticker")
            cik = entry.get("cik_str") or entry.get("cik")
            if not ticker or cik is None:
                continue
            mapping[ticker.strip().upper()] = f"{int(cik):010d}"
        return mapping
    except Exception:
        return None

def _load_map() -> Dict[str, str]:
    global _CACHE
    attempted = []
    for path in DEFAULT_PATHS:
        if not path:
            continue
        attempted.append(path)
        if os.path.isfile(path):
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
    # If nothing was loaded, try the SEC map as a last-resort source for curated tickers too.
    sec = _load_sec_map()
    if sec:
        return sec
    # Preserve empty cache but log where we looked; callers surface clearer errors.
    if attempted:
        import logging

        logging.getLogger(__name__).warning("ticker_cik.csv not found in any path: %s", attempted)
    return _CACHE[0]


def _load_sec_map() -> Dict[str, str]:
    """Load the full SEC ticker → CIK dataset if present."""
    global _SEC_CACHE
    attempted = []
    for path in SEC_TICKER_PATHS:
        if not path or not os.path.isfile(path):
            continue
        attempted.append(path)
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
        # SEC JSON is keyed by index; each entry has ticker + cik_str.
        for entry in data.values():
            ticker = entry.get("ticker")
            cik = entry.get("cik_str") or entry.get("cik")
            if not ticker or cik is None:
                continue
            mapping[ticker.strip().upper()] = f"{int(cik):010d}"

        if mapping:
            _SEC_CACHE = (mapping, mtime)
            return mapping
    # If nothing is present locally, try to fetch and persist once or when cache is empty.
    for target in SEC_DOWNLOAD_TARGETS:
        if not target:
            continue
        downloaded = _download_sec_tickers(target)
        if downloaded:
            _SEC_CACHE = (downloaded, os.path.getmtime(target) if os.path.isfile(target) else None)
            return downloaded
    if attempted:
        import logging

        logging.getLogger(__name__).warning("company_tickers.json not found in any path: %s", attempted)
    return _SEC_CACHE[0]


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    t = ticker.strip().upper()
    # Prefer the curated list first.
    mapping = _load_map()
    if t in mapping:
        return mapping[t]
    # Fall back to the broad SEC list if available.
    sec = _load_sec_map()
    return sec.get(t) if sec else None


def get_coverage_status(ticker: str) -> bool:
    """Return True if the ticker is in our curated IR coverage list."""
    if not ticker:
        return False
    return ticker.strip().upper() in _load_map()


def list_supported_tickers() -> Dict[str, str]:
    return _load_map()
