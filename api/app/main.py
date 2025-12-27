import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from redis import Redis
from rq import Queue

from .mock_data import MOCK_MODEL
from .db import get_filing_by_accession, list_filings_by_ticker
from .ticker_map import get_cik_for_ticker, get_coverage_status, list_supported_tickers
from .facts import list_facts_by_ticker
from .canonical import list_canonical_by_ticker
from .model import get_model
from .statements import get_statements_for_ticker
from .summary import get_summary

app = FastAPI(title="deltaisland research API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    covered: bool


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
    xbrl_tag: str | None = None
    context_ref: str | None = None
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
    source_xbrl_tag: str | None = None
    source_context_ref: str | None = None
    created_at: datetime | None


class ModelValue(BaseModel):
    value: float | None
    unit: str | None
    source: Optional[Dict[str, Any]] = None


class ModelPeriod(BaseModel):
    period_end: str
    values: Dict[str, ModelValue]
    scenario: Optional[str] = None
    period_index: Optional[int] = None
    assumptions: Optional[Dict[str, Optional[float]]] = None


class ModelStatement(BaseModel):
    actuals: List[ModelPeriod]
    forecast: List[ModelPeriod]


class ModelResponse(BaseModel):
    ticker: str
    as_of: Optional[str] = None
    drivers: Dict[str, Dict]
    scenarios: List[str]
    statements: Dict[str, ModelStatement]
    forecast_summary: Optional[Dict[str, Any]] = None
    coverage: Optional[Dict[str, Any]] = None
    backtest_time_travel: Optional[Dict[str, Any]] = None


class StatementLine(BaseModel):
    line_item: str | None
    value: float | None
    unit: str | None
    source_accession: str | None = None
    source_path: str | None = None
    source_xbrl_tag: str | None = None
    source_context_ref: str | None = None
    source_form: str | None = None
    source_filed_at: date | None = None


class StatementPeriod(BaseModel):
    period_start: str | None = None
    period_end: str
    lines: dict[str, list[StatementLine]]


class SummaryPeriod(BaseModel):
    period_end: str
    values: dict[str, dict]


class SummaryResponse(BaseModel):
    ticker: str
    periods: List[SummaryPeriod]
    filings: List[dict]
    covered: bool
    resolvable: bool
    cik: str | None
    derived: dict | None = None
    drivers: dict | None = None
    forecast: List[dict] | None = None
    dropped_facts: int | None = None
    coverage: dict | None = None
    ties: dict | None = None
    backtest: dict | None = None
    backtest_time_travel: dict | None = None


class TriggerResponse(BaseModel):
    ticker: str
    ingest_job_id: str | None
    parse_job_id: str | None
    canonical_job_id: str | None
    queue: str
    covered: bool
    dropped_facts: int | None = None


class BacktestResponse(BaseModel):
    ticker: str
    backtest: dict | None = None
    backtest_time_travel: dict | None = None


class QualityResponse(BaseModel):
    ticker: str
    coverage: dict | None = None
    ties: dict | None = None
    backtest_time_travel: dict | None = None


@app.get("/health", tags=["health"])
def health() -> dict:
    """Lightweight readiness probe."""
    return {"status": "ok"}


@app.get("/artifact", tags=["ingest"])
def get_artifact(path: str):
    """Serve a stored artifact from RAW_STORAGE_ROOT, with basic path safety."""
    storage_root = Path(os.getenv("RAW_STORAGE_ROOT", "storage/raw")).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(storage_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Requested path outside storage root")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


@app.get("/mock/model", response_model=MockModel, tags=["mock"])
def mock_model() -> MockModel:
    """Serve a deterministic model snapshot for the prototype UI."""
    return MOCK_MODEL  # type: ignore[return-value]


@app.get("/tickers", tags=["ingest"])
def supported_tickers() -> dict:
    """List supported tickers and CIKs from the local mapping."""
    return list_supported_tickers()


@app.post("/ingest/{ticker}", response_model=EnqueueResponse, tags=["ingest"])
def enqueue_ingest(ticker: str, limit: int = 8) -> EnqueueResponse:
    """Queue a fetch job for a ticker. Worker must be running to process."""
    cik = get_cik_for_ticker(ticker)
    covered = get_coverage_status(ticker)
    if not cik:
        raise HTTPException(
            status_code=404,
            detail="Ticker not found in SEC ticker list. Ensure company_tickers.json is present.",
        )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        redis_conn = Redis.from_url(redis_url)
        q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
        job = q.enqueue("workers.jobs.fetch_filings.fetch_latest_filings", ticker, limit=limit)
        return EnqueueResponse(ticker=ticker.upper(), cik=cik, covered=covered, job_id=job.id, queue=q.name)
    except Exception:
        # Fall back to inline execution if Redis/worker is not available and workers package is present.
        try:
            from workers.jobs.run_pipeline import run_pipeline  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime guard
            raise HTTPException(
                status_code=503,
                detail=f"Ingestion unavailable (queue down and workers module missing in API image): {exc}",
            )
        run_pipeline(ticker, limit=limit)
        return EnqueueResponse(ticker=ticker.upper(), cik=cik, covered=covered, job_id=None, queue="inline")


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
    try:
        data = get_summary(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load summary for {ticker}: {exc}")
    return data


@app.get("/quality/{ticker}", response_model=QualityResponse, tags=["summary"])
def quality(ticker: str) -> QualityResponse:
    try:
        data = get_summary(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load quality for {ticker}: {exc}")
    return QualityResponse(
        ticker=data.get("ticker", ticker.upper()),
        coverage=data.get("coverage"),
        ties=data.get("ties"),
        backtest_time_travel=data.get("backtest_time_travel"),
    )


@app.get("/backtest/{ticker}", response_model=BacktestResponse, tags=["backtest"])
def backtest(ticker: str) -> BacktestResponse:
    try:
        data = get_summary(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load backtest for {ticker}: {exc}")
    return BacktestResponse(
        ticker=ticker.upper(),
        backtest=data.get("backtest"),
        backtest_time_travel=data.get("backtest_time_travel"),
    )


@app.get("/model/{ticker}", response_model=ModelResponse, tags=["model"])
def model(ticker: str, actuals_limit: int = 4) -> ModelResponse:
    try:
        data = get_model(ticker, actuals_limit=actuals_limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load model for {ticker}: {exc}")
    return data


@app.post("/trigger/{ticker}", response_model=TriggerResponse, tags=["ingest"])
def trigger_ingest_pipeline(ticker: str, limit: int = 8) -> TriggerResponse:
    """Trigger ingest -> parse -> canonical materialization for a ticker (default last 8 filings)."""
    cik = get_cik_for_ticker(ticker)
    covered = get_coverage_status(ticker)
    if not cik:
        raise HTTPException(
            status_code=404,
            detail="Ticker not found in SEC ticker list. Ensure company_tickers.json is present.",
        )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        redis_conn = Redis.from_url(redis_url)
        q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
        pipeline_job = q.enqueue("workers.jobs.run_pipeline.run_pipeline", ticker, limit=limit)
        return TriggerResponse(
            ticker=ticker.upper(),
            covered=covered,
            ingest_job_id=pipeline_job.id,
            parse_job_id=pipeline_job.id,
            canonical_job_id=pipeline_job.id,
            queue=q.name,
            dropped_facts=None,
        )
    except Exception:
        # If Redis/worker is unavailable, try to run inline if workers module is present.
        try:
            from workers.jobs.run_pipeline import run_pipeline  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime guard
            raise HTTPException(
                status_code=503,
                detail=f"Ingestion unavailable (queue down and workers module missing in API image): {exc}",
            )
        result = run_pipeline(ticker, limit=limit)
        return TriggerResponse(
            ticker=ticker.upper(),
            covered=covered,
            ingest_job_id=None,
            parse_job_id=None,
            canonical_job_id=None,
            queue="inline",
            dropped_facts=result.get("dropped_facts") if isinstance(result, dict) else None,
        )


@app.post("/backfill/{ticker}", response_model=TriggerResponse, tags=["ingest"])
def trigger_backfill_pipeline(ticker: str, limit: int = 24) -> TriggerResponse:
    """Trigger backfill ingest -> parse -> canonical materialization for older filings."""
    cik = get_cik_for_ticker(ticker)
    covered = get_coverage_status(ticker)
    if not cik:
        raise HTTPException(
            status_code=404,
            detail="Ticker not found in SEC ticker list. Ensure company_tickers.json is present.",
        )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        redis_conn = Redis.from_url(redis_url)
        q = Queue(os.getenv("QUEUE_NAME", "ingest"), connection=redis_conn)
        pipeline_job = q.enqueue("workers.jobs.backfill_ticker.backfill_ticker", ticker, limit=limit)
        return TriggerResponse(
            ticker=ticker.upper(),
            covered=covered,
            ingest_job_id=pipeline_job.id,
            parse_job_id=pipeline_job.id,
            canonical_job_id=pipeline_job.id,
            queue=q.name,
            dropped_facts=None,
        )
    except Exception:
        try:
            from workers.jobs.backfill_ticker import backfill_ticker  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime guard
            raise HTTPException(
                status_code=503,
                detail=f"Backfill unavailable (queue down and workers module missing in API image): {exc}",
            )
        result = backfill_ticker(ticker, limit=limit)
        return TriggerResponse(
            ticker=ticker.upper(),
            covered=covered,
            ingest_job_id=None,
            parse_job_id=None,
            canonical_job_id=None,
            queue="inline",
            dropped_facts=result.get("dropped_facts") if isinstance(result, dict) else None,
        )
