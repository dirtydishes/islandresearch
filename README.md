# deltaisland research

Public-filings sell-side model compiler: ingest EDGAR data, normalize financials, tie a 3‑statement model, and generate driver-based forecasts with audit trails. Valuation output currently exists only in the mock prototype.

## Current status
- Compose stack runs `api`, `worker`, `frontend`, `db`, `redis`, `minio`, plus a scheduler for nightly incremental + weekly strict backfills; `.env.example` seeds defaults.
- Ingestion: `/ingest/{ticker}`, `/trigger/{ticker}`, and `/backfill/{ticker}` fetch and persist filings into `storage/raw/` (append-only) and `filings` in Postgres. Curated `data/ticker_cik.csv` is primary; SEC `company_tickers.json` can auto-download as fallback.
- Parsing: inline XBRL extractor with context/segment filtering, unit normalization, sign handling, and fiscal-period span normalization; HTML fallback for tables; refetches primary HTML when only an index is saved. Outputs `facts` with `source_path`.
- Canonicalization: expanded GAAP tag map (IS/BS/CF + shares/EPS + working capital + debt/equity), derived residuals, cash‑flow period alignment, and strict tie checks. Statement display order is enforced; `/statements` and `/summary` include provenance.
- Model: driver-based 3‑statement forecast with base/bull/bear scenarios, forecast ranges, and driver provenance (`/summary`, `/model`).
- Quality: coverage counts + missing items, balance‑sheet/cash‑flow tie deltas, and backtests (revenue, EPS, margins; including time‑travel) surfaced via `/summary`, `/quality`, `/backtest`.
- Parity: `api/scripts/parity_check.py` compares `/summary` coverage with `/statements` counts and checks period-start consistency.
- Frontend: `/` shows statements with period selector, coverage/ties, driver inputs, and source pills with hover details; `/model` shows the driver-based model view; `/mock` remains a deterministic fallback.

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

## Quickstart (live pipeline)
1) Queue ingest + parse + canonical: `POST http://localhost:8000/trigger/AAPL?limit=8`.
2) Statements: `GET http://localhost:8000/statements/AAPL?limit=8`.
3) Summary + drivers + forecast: `GET http://localhost:8000/summary/AAPL`.
4) Model view: `GET http://localhost:8000/model/AAPL?actuals_limit=4`.
5) Quality checks: `GET http://localhost:8000/quality/AAPL`.

## API walkthrough (curl)
```sh
curl -X POST "http://localhost:8000/trigger/AAPL?limit=8"
curl "http://localhost:8000/filings/AAPL"
curl "http://localhost:8000/statements/AAPL?limit=8"
curl "http://localhost:8000/summary/AAPL"
curl "http://localhost:8000/model/AAPL?actuals_limit=4"
curl "http://localhost:8000/quality/AAPL"
curl "http://localhost:8000/backtest/AAPL"
```

## Service entrypoints
- API: FastAPI at `api/app/main.py` (`uvicorn app.main:app --reload`).
- Workers: RQ worker runner at `workers/queue.py`.
- Scheduler: `workers/jobs/scheduler.py` (nightly + weekly backfill loop).
- Frontend: Next.js app under `frontend/src/` (`bun dev` or `npm run dev` if bun unavailable).

## Development setup (local)
- Recommended Python: 3.11 or 3.12 (psycopg 3 binary wheels are pinned to avoid source builds).
- Create venv: `python3 -m venv .venv && source .venv/bin/activate`.
- Install worker deps: `pip install -r workers/requirements.txt` (ensure Homebrew `libpq`/Postgres is installed so `pg_config` exists if wheels are missing).
- Run worker unit tests: `source .venv/bin/activate && python3 -m unittest discover workers/tests`.
- Run API tests: `docker compose -f infra/compose/docker-compose.yml run --rm api pytest --maxfail=1`.
- Run frontend tests: `docker compose -f infra/compose/docker-compose.yml run --rm frontend bun test`.
- Start services with Compose for API/DB/Redis/MinIO: `docker compose -f infra/compose/docker-compose.yml up --build`.

## Ingestion (ticker → EDGAR fetch)
- Ticker map lives in `data/ticker_cik.csv`; override with `TICKER_CIK_PATH`. SEC `company_tickers.json` is a fallback (auto-downloads if missing).
- Queue a fetch job: `POST http://localhost:8000/ingest/AAPL` (optionally `?limit=8`). Requires worker + Redis running.
- Trigger full pipeline (fetch → parse → canonical): `POST http://localhost:8000/trigger/AAPL`.
- Backfill older filings: `POST http://localhost:8000/backfill/AAPL?limit=24`.
- List supported tickers: `GET http://localhost:8000/tickers`.
- Worker job saves SEC submissions JSON, filing index, and primary HTML into `storage/raw/{cik}/` and records metadata in Postgres (`filings` table). Raw artifacts are append-only.
- Query stored filings: `GET http://localhost:8000/filings/AAPL`.
- Fetch a stored artifact: `GET http://localhost:8000/artifact?path=storage/raw/{cik}/{accession}_primary.html`.
- CLI alternative (inside repo): `python -m workers.jobs.fetch_filings AAPL --limit 2 --storage-root storage/raw`.

## Parsing
- Parser is XBRL-first: extracts GAAP tags across IS/BS/CF with periods, units, and iXBRL sign handling into `facts`.
- Context filtering drops disallowed segment axes; unit normalization standardizes USD/shares/USDPERSHARE.
- Fallback re-fetches primary HTML if only an index file was saved.
- Trigger parse via worker job (after a filing is fetched): enqueue `workers.jobs.parse_filing.parse_filing` with `accession`, `cik`, `ticker`, `html_path`.
- API to list parsed facts: `GET http://localhost:8000/facts/AAPL`.
- API to queue parse job for stored accession: `POST http://localhost:8000/parse/{accession}`.

## Canonical facts
- Worker job to aggregate parsed facts into `canonical_facts`: enqueue `workers.jobs.materialize_canonical.run_materialization` with `ticker`.
- API to list canonical facts: `GET http://localhost:8000/canonical/AAPL`.
- Canonicalization normalizes units/period types, aligns cash‑flow spans, adds residuals, and runs tie checks (balance sheet + cash flow).
- Tie behavior is configurable via env: `TIE_TOLERANCE`, `RESIDUAL_TOLERANCE`, `HARD_FAIL_TIES`.

## Model & quality outputs
- `/summary/{ticker}` returns canonical values, derived metrics, driver inputs + provenance, forecast scenarios, coverage, and tie deltas.
- `/model/{ticker}` groups actuals/forecasts by statement and includes forecast ranges.
- `/quality/{ticker}` and `/backtest/{ticker}` expose coverage, tie checks, and time‑travel revenue backtests.

## Backfill & scheduler
- Ad‑hoc full backfill: `python -m workers.jobs.backfill_all --limit 8 --strict-ties`.
- Recent incremental backfill: `python -m workers.jobs.backfill_recent --limit 4`.
- Per‑ticker backfill: `python -m workers.jobs.backfill_ticker AAPL --limit 24`.
- Parity check (API vs statements): `python scripts/parity_check.py --max-tickers 10`.
- Scheduler runs nightly (`BACKFILL_NIGHTLY_TIME_UTC`, `BACKFILL_NIGHTLY_LIMIT`, optional `BACKFILL_NIGHTLY_TICKERS`) and weekly (`BACKFILL_WEEKLY_DAY`, `BACKFILL_WEEKLY_TIME_UTC`, `BACKFILL_WEEKLY_LIMIT`) with strict ties on weekly runs.

## Scheduler & tie env vars
- `BACKFILL_NIGHTLY_ENABLED` / `BACKFILL_WEEKLY_ENABLED` (default true)
- `BACKFILL_NIGHTLY_TIME_UTC` (default `02:00`)
- `BACKFILL_NIGHTLY_LIMIT` (default `4`)
- `BACKFILL_NIGHTLY_TICKERS` (comma-separated, optional)
- `BACKFILL_WEEKLY_DAY` (default `SUN`)
- `BACKFILL_WEEKLY_TIME_UTC` (default `03:00`)
- `BACKFILL_WEEKLY_LIMIT` (default `8`)
- `TIE_TOLERANCE` (default `1e-2`)
- `RESIDUAL_TOLERANCE` (default `1e-2`)
- `HARD_FAIL_TIES` (default `false`)

## Next steps
- Expand GAAP coverage for sector-specific line items and restatements; improve provenance down to XBRL context/table row.
- Extend backtesting beyond revenue (EPS, margins) and add interval‑coverage targets.
- Add valuation outputs (DCF + multiples) and surface them alongside the model view.
- Scale coverage to 200–500 tickers with stricter ingestion throttling and retry/observability.
