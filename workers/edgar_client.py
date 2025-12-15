import os
import pathlib
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_USER_AGENT = os.getenv(
    "EDGAR_USER_AGENT", "deltaisland-research/0.1 (contact@example.com)"
)


class EDGARClient:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    def get_submissions(self, cik: str) -> Dict[str, Any]:
        norm_cik = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{norm_cik}.json"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)  # be gentle
        return resp.json()

    def get_filing(self, cik: str, accession: str) -> bytes:
        # accession in submissions JSON has no dashes; transform for path.
        no_dashes = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{no_dashes}/{accession}-index.html"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.content


class StorageWriter:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = pathlib.Path(root or os.getenv("RAW_STORAGE_ROOT", "storage/raw")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, cik: str, accession: str, content: bytes, suffix: str = "html") -> str:
        dir_path = self.root / cik
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{accession}.{suffix}"
        file_path.write_bytes(content)
        return str(file_path)

    def save_json(self, cik: str, name: str, data: Dict[str, Any]) -> str:
        import json

        dir_path = self.root / cik
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{name}.json"
        file_path.write_text(json.dumps(data, indent=2))
        return str(file_path)
