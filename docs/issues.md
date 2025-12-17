# Issue Backlog (next steps)

## 1) Expand parsing + canonical schema with tests
- Scope: broaden inline XBRL tag coverage, normalize contexts/units/periods, and formalize canonical line items.
- Tasks:
  - Add richer tag map and context handling (instant vs duration, unit normalization).
  - Define canonical schema mapping for key IS/BS/CF lines and shares; document in code.
  - Create deterministic parser fixtures from saved filings in `storage/raw/` and add tests for parser + canonical materialization (unit tests started under `workers/tests/`; expand with real filings).
- Done when: parser tests cover target tags/period alignment; canonical rows are stable per fixture; lint/tests pass in CI; schema documented.

## 2) Harden ingest/parse pipeline and hygiene
- Scope: reliability/observability and repo cleanliness.
- Tasks:
  - Add retries/metrics/logging to RQ jobs; surface failure states.
  - Guard storage writes (idempotent paths, ensure missing dirs handled).
  - Update gitignore to exclude `.next/`, `__pycache__/`, compiled assets.
  - Document ingest→parse flow and expected artifacts.
- Done when: jobs are retry-safe with metrics/logging, repo is clean after dev build, and a short runbook exists.

## 3) Replace stub forecast and expose provenance
- Scope: move from +2% placeholder to driver-based outputs and show “receipts” per number.
- Tasks:
  - Implement driver extraction from canonical facts (growth, margins, WC, capex, shares).
  - Add API output with assumptions + derived values; include source links/ids.
  - Update UI to display provenance/audit trail per metric and the driver-based forecast.
- Done when: forecast uses drivers from canonical data, assumptions returned via API, UI shows provenance for displayed numbers.

## 4) Backtesting harness (time-travel)
- Scope: enforce time-travel correctness before ML work.
- Tasks:
  - Build fixtures that freeze data as-of dates and replay forecasts.
  - Compute MAE/MAPE/directional/coverage metrics per ticker/prediction type.
  - Add gating: fail if coverage/accuracy thresholds regress.
- Done when: harness runs on fixtures, reports metrics, and can fail builds on regressions; Python version/tooling documented (psycopg 3 binary pinned; prefer 3.11/3.12 for smooth wheels).
