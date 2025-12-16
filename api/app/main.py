import os
from datetime import date, datetime
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from rq import Queue

from .mock_data import MOCK_MODEL
from .db import get_filing_by_accession, list_filings_by_ticker
from .ticker_map import get_cik_for_ticker, list_supported_tickers
from .facts import list_facts_by_ticker
from .canonical import list_canonical_by_ticker
from .statements import get_statements_for_ticker
from .summary import get_summary


app = FastAPI(title="deltaisland research API", version="0.1.0")


class StatementRow(BaseModel):
    period: str
    revenue: float
    ebitda: float
    net_income: float
    cash: float
    debt: float


class ForecastRow(StatementRow):
    fcf: float


class Valuation(BaseModel):
    enterprise_value: float
    equity_value: float
    shares_outstanding: float
    implied_share_price: float
    notes: str


class MockModel(BaseModel):
    company: str
    as_of: str
    statements: List[StatementRow]
    forecast: List[ForecastRow]
    valuation: Valuation
    audit_summary: List[str]


class EnqueueResponse(BaseModel):
    ticker: str
    cik: str
    job_id: str
    queue: str


class ParseEnqueueResponse(BaseModel):
    accession: str
    ticker: str
    cik: str
    path: str
    job_id: str
    queue: str


class Filing(BaseModel):
    ticker: str
    cik: str
    accession: str
    form: str | None
    filed_at: date | None
    path: str | None
    submissions_path: str | None
    created_at: datetime | None


class Fact(BaseModel):
    accession: str
    cik: str
    ticker: str
    period_end: date | None
    period_type: str | None
    statement: str | None
    line_item: str | None
    value: float | None
    unit: str | None
    source_path: str | None
    created_at: datetime | None


class CanonicalFact(BaseModel):
    ticker: str
    cik: str
    accession: str
    period_end: date | None
    period_type: str | None
    statement: str | None
    line_item: str | None
    value: float | None
    unit: str | None
    source_fact_id: int | None
    created_at: datetime | None


class StatementLine(BaseModel):
    line_item: str | None
    value: float | None
    unit: str | None


class StatementPeriod(BaseModel):
    period_end: str
    lines: dict[str, list[StatementLine]]


class SummaryPeriod(BaseModel):
    period_end: str
    values: dict[str, dict]


class SummaryResponse(BaseModel):
    ticker: str
    periods: List[SummaryPeriod]
    filings: List[dict]


class TriggerResponse(BaseModel):
    ticker: str
    ingest_job_id: str | None
    parse_job_id: str | None
    canonical_job_id: str | None
    queue: str


@app.get("/health", tags=["health"])
def health() -> dict:
    """Lightweight readiness probe."""
    return {"status": "ok"}


@app.get("/mock/model", response_model=MockModel, tags=["mock"])
def mock_model() -> MockModel:
    """Serve a deterministic model snapshot for the prototype UI."""
    return MOCK_MODEL  # type: ignore[return-value]


@app.get("/tickers", tags=["ingest"])
def supported_tickers() -> dict:
    """List supported tickers and CIKs from the local mapping."""
    return list_supported_tickers()


@app.post("/ingest/{ticker}", response_model=EnqueueResponse, tags=["ingest"])
def enqueue_ingest(ticker: str, limit: int = 3) -> EnqueueResponse:
    """Queue a fetch job for a ticker. Worker must be running to process."""
    cik = get_cik_for_ticker(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail="Ticker not found in mapping")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_conn = Redis.from_url(redis_url)
    q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
    job = q.enqueue("workers.jobs.fetch_filings.fetch_latest_filings", ticker, limit=limit)
    return EnqueueResponse(ticker=ticker.upper(), cik=cik, job_id=job.id, queue=q.name)


@app.get("/filings/{ticker}", response_model=List[Filing], tags=["ingest"])
def get_filings(ticker: str) -> List[Filing]:
    """List stored filings for a ticker from Postgres."""
    rows = list_filings_by_ticker(ticker)
    if not rows:
        raise HTTPException(status_code=404, detail="No filings stored for ticker")
    return rows


@app.get("/facts/{ticker}", response_model=List[Fact], tags=["parse"])
def get_facts(ticker: str) -> List[Fact]:
    """List parsed facts for a ticker from Postgres."""
    rows = list_facts_by_ticker(ticker)
    if not rows:
        raise HTTPException(status_code=404, detail="No facts stored for ticker")
    return rows


@app.post("/parse/{accession}", response_model=ParseEnqueueResponse, tags=["parse"])
def enqueue_parse(accession: str) -> ParseEnqueueResponse:
    """Queue a parse job for a stored filing accession."""
    filing = get_filing_by_accession(accession)
    if not filing:
        raise HTTPException(status_code=404, detail="Accession not found")
    path = filing.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="No stored path for accession")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_conn = Redis.from_url(redis_url)
    q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
    job = q.enqueue(
        "workers.jobs.parse_filing.parse_filing",
        accession,
        filing["cik"],
        filing["ticker"],
        path,
    )
    return ParseEnqueueResponse(
        accession=accession,
        ticker=filing["ticker"],
        cik=filing["cik"],
        path=path,
        job_id=job.id,
        queue=q.name,
    )


@app.get("/canonical/{ticker}", response_model=List[CanonicalFact], tags=["canonical"])
def get_canonical(ticker: str) -> List[CanonicalFact]:
    """List canonical facts for a ticker."""
    rows = list_canonical_by_ticker(ticker)
    if not rows:
        raise HTTPException(status_code=404, detail="No canonical facts stored for ticker")
    return rows


@app.get("/statements/{ticker}", response_model=Dict[str, List[StatementPeriod]], tags=["statements"])
def get_statements(ticker: str, limit: int = 8) -> Dict[str, List[StatementPeriod]]:
    """Return statement-friendly periods assembled from canonical facts."""
    data = get_statements_for_ticker(ticker, limit=limit)
    if not data["periods"]:
        # Return empty structure rather than 404 to aid troubleshooting.
        return {"periods": []}
    return data


@app.get("/summary/{ticker}", response_model=SummaryResponse, tags=["summary"])
def summary(ticker: str) -> SummaryResponse:
    data = get_summary(ticker)
    # Return empty structures instead of 404 so UI can show graceful empty state.
    return data


@app.post("/trigger/{ticker}", response_model=TriggerResponse, tags=["ingest"])
def trigger_ingest_pipeline(ticker: str, limit: int = 1) -> TriggerResponse:
    """Trigger ingest -> parse -> canonical materialization for a ticker."""
    cik = get_cik_for_ticker(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail="Ticker not found in mapping")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_conn = Redis.from_url(redis_url)
    q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
    pipeline_job = q.enqueue("workers.jobs.run_pipeline.run_pipeline", ticker, limit=limit)
    return TriggerResponse(
        ticker=ticker.upper(),
        ingest_job_id=pipeline_job.id,
        parse_job_id=pipeline_job.id,
        canonical_job_id=pipeline_job.id,
        queue=q.name,
    )
