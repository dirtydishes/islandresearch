# deltaisland research

Public-filings sell-side model reverse-engineering and forecasting platform: ingest EDGAR data, normalize financials, generate an auditable 3-statement forecast, valuation, and scenario outputs.

## Docs
- Core principles: `docs/principles.md`
- MVP scope: `docs/mvp-scope.md`
- Full roadmap: `plan.md`

## Quickstart (mock prototype)
1) Copy `.env.example` to `.env` and adjust secrets if needed (MinIO secrets must be ≥8 chars).
2) Start services: `docker compose -f infra/compose/docker-compose.yml up --build`.
3) API mock: GET `http://localhost:8000/mock/model` returns deterministic historicals, forecast, and valuation.
4) Frontend mock: visit `http://localhost:3000/mock` to see the demo UI backed by the mock endpoint (falls back to an offline stub if API is down).

## Service entrypoints
- API: FastAPI at `api/app/main.py` (`uvicorn app.main:app --reload`).
- Workers: RQ worker runner at `workers/queue.py`.
- Frontend: Next.js app under `frontend/src/` (`bun dev` or `npm run dev` if bun unavailable).

## Ingestion (ticker → EDGAR fetch)
- Ticker map lives in `data/ticker_cik.csv`; override with `TICKER_CIK_PATH` if needed.
- Queue a fetch job: `POST http://localhost:8000/ingest/AAPL` (optionally `?limit=2`). Requires worker + Redis running.
- List supported tickers: `GET http://localhost:8000/tickers`.
- Worker job saves SEC submissions JSON and filings HTML into `storage/raw/{cik}/` and records metadata in Postgres (`filings` table).
- Query stored filings: `GET http://localhost:8000/filings/AAPL`.
- CLI alternative (inside repo): `python -m workers.jobs.fetch_filings AAPL --limit 2 --storage-root storage/raw`.

## Parsing (demo)
- Minimal parser extracts revenue/net_income/ebitda heuristically from HTML tables into `facts` table.
- Trigger parse via worker job (after a filing is fetched): enqueue `workers.jobs.parse_filing.parse_filing` with `accession`, `cik`, `ticker`, `html_path` (see saved paths in `storage/raw/{cik}/`).
- API to list parsed facts: `GET http://localhost:8000/facts/AAPL`.
- API to queue parse job for stored accession: `POST http://localhost:8000/parse/{accession}` (uses stored path from filings table).
