# Repository Guidelines

## Project Structure & Module Organization
- Current artifact is the blueprint in `plan.md`; update it when scope or architecture shifts.
- Target layout: `api/` (FastAPI), `workers/` (ingestion + queues), `frontend/` (Next.js + bun), `infra/` (Docker compose + IaC), `docs/` (contracts, ADRs), `storage/` (raw filings append-only, derived data versioned).
- Co-locate tests beside sources (`api/app/ingest.py` → `api/app/tests/test_ingest.py`); keep modules small and single-purpose.

## Build, Test, and Development Commands
- Prefer Compose when available: `docker compose up api frontend worker db redis objectstore` to mirror prod deps.
- API: `cd api && uvicorn app.main:app --reload`; secrets come from `.env` templated by `.env.example`.
- Frontend: `cd frontend && bun install && bun dev`.
- Workers: `docker compose run worker python -m app.jobs.seed_cik_map`; ensure Redis is up before enqueueing.

## Coding Style & Naming Conventions
- Python: 4-space indent, type hints, snake_case for functions/vars, PascalCase for classes; run `ruff` + `black` (`bunx ruff check api`).
- TypeScript/React: 2-space indent, strict mode, function components + hooks; camelCase variables, PascalCase components; files kebab-case (`ticker-search.tsx`).
- Keep ingestion/parsing isolated from modeling; prefer pure functions over implicit globals.

## Testing Guidelines
- API/backend: `docker compose run api pytest --maxfail=1`; fixtures must be deterministic and time-travel-safe.
- Frontend: `docker compose run frontend bun test`; add Playwright for multi-page flows.
- Name tests by behavior (`test_parses_cash_flow_html_table`); cover restatements, split-adjusted shares, and reconciliation edge cases.
- Add tests with new features; if deferred, document the gap in the PR.

## Commit & Pull Request Guidelines
- Use Conventional Commits (`feat: ingest 10-Q package`, `fix: handle negative gross margin parsing`) to keep history searchable.
- Keep PRs small; include a short description, linked issue, before/after notes, and screenshots for UI changes.
- Call out data risks (EDGAR rate limits, parsing assumptions) and add repro steps for bugfixes.
- Run linters/tests before opening; CI should stay green.

## Security & Configuration Tips
- Never commit secrets; use `.env.local` ignored by git and provide sanitized defaults in `.env.example`.
- Treat raw filings as append-only; do not overwrite source artifacts—write new versions and reference provenance.
- Respect external data policies: throttle EDGAR fetches and cache responses to avoid abuse; validate user inputs before queueing jobs.
