# deltaisland research

Public-filings sell-side model reverse-engineering and forecasting platform: ingest EDGAR data, normalize financials, generate an auditable 3-statement forecast, valuation, and scenario outputs.

## Current status
- Compose stack runs api/worker/frontend/db/redis/minio; `.env.example` seeds local defaults.
- Ingestion: enqueue `/ingest/{ticker}` or `/trigger/{ticker}` to fetch recent 10-K/10-Q HTML into `storage/raw/` and record filings in Postgres.
- Parsing: minimal inline XBRL + HTML table scrape writes demo facts; canonical stage aggregates per period/tag and computes derived ratios + a stub +2% forecast for `/summary`.
- Frontend: `/` shows canonical statements, derived metrics, filings list, and a simple forecast; `/mock` uses deterministic mock data and falls back if API is down.

## Docs
- Core principles: `docs/principles.md`
- MVP scope: `docs/mvp-scope.md`
- Full roadmap: `plan.md`
- Issue backlog: `docs/issues.md`
- Canonical schema: `docs/canonical-schema.md`

## Quickstart (mock prototype)
1) Copy `.env.example` to `.env` and adjust secrets if needed (MinIO secrets must be ≥8 chars).
2) Start services: `docker compose -f infra/compose/docker-compose.yml up --build`.
3) API mock: GET `http://localhost:8000/mock/model` returns deterministic historicals, forecast, and valuation.
4) Frontend mock: visit `http://localhost:3000/mock` to see the demo UI backed by the mock endpoint (falls back to an offline stub if API is down).

## Service entrypoints
- API: FastAPI at `api/app/main.py` (`uvicorn app.main:app --reload`).
- Workers: RQ worker runner at `workers/queue.py`.
- Frontend: Next.js app under `frontend/src/` (`bun dev` or `npm run dev` if bun unavailable).

## Development setup (local)
- Recommended Python: 3.11 or 3.12 (psycopg 3 binary wheels are pinned to avoid source builds).
- Create venv: `python3 -m venv .venv && source .venv/bin/activate`.
- Install worker deps: `pip install -r workers/requirements.txt` (ensure Homebrew `libpq`/Postgres is installed so `pg_config` exists if wheels are missing).
- Run unit tests: `source .venv/bin/activate && python3 -m unittest discover workers/tests`.
- Start services with Compose for API/DB/Redis/MinIO: `docker compose -f infra/compose/docker-compose.yml up --build`.

## Ingestion (ticker → EDGAR fetch)
- Ticker map lives in `data/ticker_cik.csv`; override with `TICKER_CIK_PATH` if needed.
- Queue a fetch job: `POST http://localhost:8000/ingest/AAPL` (optionally `?limit=2`). Requires worker + Redis running.
- List supported tickers: `GET http://localhost:8000/tickers`.
- Worker job saves SEC submissions JSON, filing index, and primary HTML into `storage/raw/{cik}/` and records metadata in Postgres (`filings` table).
- Query stored filings: `GET http://localhost:8000/filings/AAPL`.
- CLI alternative (inside repo): `python -m workers.jobs.fetch_filings AAPL --limit 2 --storage-root storage/raw`.

## Parsing (demo)
- Parser is XBRL-first: extracts key us-gaap tags (revenue, net income, operating income, cash, assets, liabilities, equity, cash flow items) with period/end and unit into `facts`.
- Trigger parse via worker job (after a filing is fetched): enqueue `workers.jobs.parse_filing.parse_filing` with `accession`, `cik`, `ticker`, `html_path` (see saved paths in `storage/raw/{cik}/`).
- API to list parsed facts: `GET http://localhost:8000/facts/AAPL`.
- API to queue parse job for stored accession: `POST http://localhost:8000/parse/{accession}` (uses stored path from filings table).

## Canonical facts (placeholder)
- Worker job to copy parsed facts into `canonical_facts` table: enqueue `workers.jobs.materialize_canonical.run_materialization` with `ticker`.
- API to list canonical facts: `GET http://localhost:8000/canonical/AAPL`.
- Current materialization is a normalized aggregation per period/tag with basic unit/period typing; replace with richer schema and validation later.

## Next steps
- Expand XBRL coverage and formalize the canonical schema; add deterministic parser/materialization tests.
- Harden the ingest/parse pipeline with retries/metrics and gitignore build artifacts.
- Replace stub forecast with driver-based logic and surface provenance in API/UI ahead of backtesting work.
