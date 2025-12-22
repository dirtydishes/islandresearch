import os
import pathlib
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from itertools import count

import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = os.getenv(
    "EDGAR_USER_AGENT", "deltaisland-research/0.1 (contact@deltaisland.local)"
)
REQUEST_TIMEOUT = float(os.getenv("EDGAR_REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("EDGAR_MAX_RETRIES", "3"))


class EDGARClient:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=MAX_RETRIES,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_submissions(self, cik: str) -> Dict[str, Any]:
        norm_cik = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{norm_cik}.json"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        time.sleep(0.2)  # be gentle
        return resp.json()

    def get_filing_index(self, cik: str, accession: str) -> bytes:
        # accession in submissions JSON has no dashes; transform for path.
        no_dashes = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{no_dashes}/{accession}-index.html"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.content

    def resolve_primary_html(self, cik: str, accession: str, index_content: bytes) -> Optional[bytes]:
        """Find and download the primary HTML document for a filing using the index page."""
        no_dashes = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{no_dashes}/"
        soup = BeautifulSoup(index_content, "html.parser")

        # Prefer direct document links under the accession directory.
        target_prefix = f"/Archives/edgar/data/{int(cik)}/{no_dashes}/"
        for link in soup.find_all("a", href=True):
            href = link["href"]
            lower = href.lower()
            if "index" in lower:
                continue
            if not lower.endswith((".htm", ".html")):
                continue
            if target_prefix not in href:
                continue
            if "ix?doc=" in lower:
                doc_path = href.split("ix?doc=")[-1]
                url = urljoin("https://www.sec.gov", doc_path)
            else:
                url = urljoin("https://www.sec.gov", href)
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            time.sleep(0.2)
            return resp.content

        # Fallback: handle ix?doc= wrapper by dereferencing to the underlying document.
        for link in soup.find_all("a", href=True):
            href = link["href"]
            lower = href.lower()
            if not lower.endswith((".htm", ".html")):
                continue
            if "index" in lower:
                continue

            # If link is an ix viewer wrapper, strip to the underlying doc.
            if "ix?doc=" in lower:
                doc_path = href.split("ix?doc=")[-1]
                url = urljoin("https://www.sec.gov", doc_path)
            else:
                url = urljoin(base, href)

            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            time.sleep(0.2)
            return resp.content
        return None


class StorageWriter:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = pathlib.Path(root or os.getenv("RAW_STORAGE_ROOT", "storage/raw")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _unique_path(self, dir_path: pathlib.Path, base_name: str, suffix: str) -> pathlib.Path:
        candidate = dir_path / f"{base_name}.{suffix}"
        if not candidate.exists():
            return candidate
        for i in count(1):
            alt = dir_path / f"{base_name}_{i}.{suffix}"
            if not alt.exists():
                return alt
        raise RuntimeError("Unable to allocate unique storage path")

    def save_bytes(self, cik: str, accession: str, content: bytes, suffix: str = "html") -> str:
        dir_path = self.root / cik
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = self._unique_path(dir_path, accession, suffix)
        file_path.write_bytes(content)
        return str(file_path)

    def save_json(self, cik: str, name: str, data: Dict[str, Any]) -> str:
        import json

        dir_path = self.root / cik
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = self._unique_path(dir_path, name, "json")
        file_path.write_text(json.dumps(data, indent=2))
        return str(file_path)
