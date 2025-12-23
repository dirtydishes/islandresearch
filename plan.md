# deltaisland research — plan.md
## Public-Filings Sell-Side Model Compiler & Forecast Engine

---

## 0. Project Identity

**Name:** DeltaIsland Research  
**Thesis:** Markets move on deltas. We build the deltas from first principles.  
**Mental model:** a *compiler* that turns public filings into sell-side-style financial models, forecasts, and valuations — with receipts.

This is **not** an “AI stock picker.”  
This *is* a deterministic, auditable research engine that happens to generate predictions.

---

## Current State (prototype)

- Ingestion: Redis/RQ + FastAPI job enqueue; EDGAR fetcher saves submissions + primary HTML into `storage/raw/` and records filings in Postgres.
- Parsing: expanded inline XBRL + HTML table scraper writes demo facts to Postgres; handles contexts/units/scale with a refetch fallback for index-only saves.
- Canonicalization: normalized aggregation of facts by period/tag via shared helper; derived ratios and a +2% stub forecast power the `/summary` endpoint; unit tests cover parser + canonical aggregation.
- UI: Next.js page renders canonical statements, derived metrics, filings list, and a simple forecast; mock page backed by `/mock/model`.
- Infra: Compose stack stands up api/worker/frontend/db/redis/minio plus a scheduler for nightly incremental + weekly strict backfills; `.env.example` seeded; ticker coverage from curated CSV with SEC JSON fallback.
- Gaps: minimal validation/backfills, no backtests, no provenance UI, limited tag coverage beyond core tags, prefer Python 3.11/3.12 for psycopg wheels, and no production-grade audit trail.

---

## 1. Core Objective

Given a ticker symbol, the system must:

1. Ingest only legitamate, verifiable data (SEC filings, market data, scraped sell-side pdfs, proprietary/paywalled content)
2. Normalize historical financial statements (IS / BS / CF)
3. Build a **tied 3-statement model**
4. Generate forward forecasts (base / bull / bear)
5. Produce valuation outputs (DCF + multiples)
6. Output **prediction ranges** (not point estimates)
7. Provide a **full audit trail** for every number

If a number cannot explain itself, it does not exist.

---

## 2. Non-Goals (Explicit Exclusions)

- No “black box” ML predictions without interpretability
- No investment advice framing
- No UI polish before model correctness

---

## 3. Technology Stack (Opinionated)

### Runtime
- **Bun** for:
  - API server
  - CLI tooling
  - orchestration scripts
  - frontend build tooling
- **Node compatibility only where required**

### Backend (Core Logic)
- Python (financial modeling, parsing, backtesting)
- FastAPI for model-serving endpoints

### Frontend
- React / Next.js (via Bun)
- Visualization-first, spreadsheet-like UX

### Data & Infra
- Postgres (canonical financials, metadata)
- Object storage (raw filings, immutable artifacts)
- Redis (caching + job coordination)

---

## 4. Operating Principles (Hard Rules)

1. **Time-travel correctness**  
   Forecasts must only use data available as of the forecast date.

2. **Deterministic first, probabilistic later**  
   Rules → constraints → distributions → ML (in that order).

3. **Accounting integrity over cleverness**  
   Statements must tie or the build fails.

4. **Explicit uncertainty**  
   Always output ranges and scenario spreads.

5. **Every value is traceable**  
   Source filing → transformation → final value.

---

## 5. MVP Scope (What “Done” Means)

### Supported Universe
- 200–500 US equities with solid XBRL coverage

### Outputs
- 5Y annual + 12Q historical normalized financials
- 2Y quarterly forecast + 3Y annual extension
- Tied 3-statement model
- DCF valuation + market multiple context
- Prediction ranges:
  - Next quarter revenue
  - Next quarter EPS
  - FY revenue growth
  - FY gross margin
- CSV / model export
- Full audit trail UI

---

## 6. Data Sources

### Primary
- SEC EDGAR
  - 10-K
  - 10-Q
  - 8-K (select events)
- Scraped sell-side PDFs
- XBRL facts (preferred)
- Filing HTML tables (fallback)


### Market Data (Public / Licensed)
- Daily prices
- Shares outstanding / splits / dividends
- Treasury yields (discount rate inputs)

---

## 7. Data Pipeline (Compiler Stages)

### 7.1 Resolution
- Ticker → CIK → company metadata
- Maintain historical ticker mappings

### 7.2 Ingestion
1. Fetch filing index by CIK
2. Download filing package
3. Store raw artifacts immutably

### 7.3 Parsing
- XBRL-first extraction:
  - values
  - units
  - periods
  - contexts
- HTML table fallback with heuristics

### 7.4 Normalization
- Fiscal calendar alignment
- Unit normalization (USD base)
- Restatement handling (versioned facts)
- Share count normalization
- GAAP-consistent line-item mapping

### 7.5 Canonicalization
Store all values in a **canonical financial schema** with:
- statement type
- standardized line item
- source filing
- source tag / table
- version
- derivation logic (if computed)

---

## 8. Canonical Financial Model (MVP)

### Statements
- Income Statement
- Balance Sheet
- Cash Flow Statement

### Derived Metrics
- Margins
- Growth rates
- Working capital ratios
- Free cash flow variants
- Return metrics (ROIC-lite)

Every derived metric must declare its formula and dependencies.

---

## 9. Forecast Engine (Sell-Side Style)

### Drivers (MVP)
- Revenue growth (trend + mean reversion)
- Gross margin (bounded)
- OpEx as % revenue
- Working capital as % revenue
- Capex as % revenue
- D&A tied to PP&E

### Forecast Logic
- Rolling historical windows
- Constraint-based projections
- Scenario perturbation (base / bull / bear)
- No unconstrained exponential growth

---

## 10. Valuation Engine

### DCF
- FCF definition configurable
- Discount rate with explicit assumptions
- Terminal growth bounds
- Sensitivity tables

### Multiples
- EV/Revenue
- EV/EBITDA
- P/E
(derived from modeled metrics + market data)

---

## 11. Prediction Framework

Predictions are **outputs of the model**, not the goal.

### Targets (MVP)
- Next-quarter revenue range
- Next-quarter EPS range
- FY revenue growth range
- FY gross margin range

### Output Requirements
- Point estimate
- 50% and 80% confidence bands
- Top 3 sensitivities

---

## 12. Backtesting & Validation (Mandatory)

### Time-Travel Harness
- Freeze dataset as-of historical dates
- Generate forecasts
- Compare to actual subsequent filings

### Metrics
- MAE / MAPE
- Directional accuracy
- Interval coverage
- Forecast stability

### Model Quality Score
- Per ticker
- Per prediction type
- Used to gate visibility of outputs

---

## 13. Frontend UX Requirements

### Core Views
1. Ticker overview
2. Historical financials
3. Model assumptions & drivers
4. Forecast & scenarios
5. Valuation
6. Audit trail

### Audit Trail UX
Click any number → see:
- Source filing link
- XBRL tag or table location
- Transformations
- Derived formulas

---

## 14. Project Structure Rules

- No code without a corresponding plan section
- Modules map 1:1 with plan sections
- No ML code until backtesting exists
- No UI polish until accounting integrity passes

---

## Near-Term Priorities

1. Parsing & canonical schema: expanded GAAP tag map (IS/BS/CF, shares/EPS, WC, debt, equity), context filtering, unit normalization, and deterministic tests with saved filings; propagate mapping/display order to API/UI.
2. Pipeline reliability: improve retry/observability for RQ jobs, guard rails on storage writes, and clean gitignore for build artifacts; add completeness counters (expected vs found line items) in `/summary`.
3. Model outputs: replace stub forecast with driver-based logic tied to canonical facts; expose provenance in API and UI (audit trail per number).
4. Backtesting harness: add time-travel fixtures and coverage metrics to validate forecasts before adding any ML.
5. Backfill/coverage: rerun ingest → parse → canonical across covered tickers (last 6–8 filings) to ensure statement parity and surface coverage in UI.

---

## Data Parity Remediation (Statements)

### Findings
- UI renders the API response verbatim; no client-side filtering or enrichment (`frontend/src/pages/index.tsx`).
- `/statements` returns raw `canonical_facts` without enrichment or ordering; DB order leaks through (`api/app/statements.py`).
- Parser and canonicalization previously relied on a very small hard-coded tag set, dropping most GAAP facts before they could reach the UI (`workers/parser.py`, `workers/canonical.py`, `api/app/summary_utils.py`).
- Pipeline fetch/parse defaults to a single filing (`run_pipeline` limit=1), leaving shallow history.
- NVDA fixture shows many unmapped contexts/tags, so most line items never materialized (`storage/raw/0001045810/000104581025000230_primary.html`).
- Root cause: minimal GAAP coverage → facts/canonical_facts nearly empty → UI shows only the few mapped tags.

### Remediation (remaining)
1. Backfill & depth
   - Bump ingest/parse limit to last 6–8 filings per ticker and add a backfill job for historical accessions to populate a full history.
2. Completeness reporting
   - Compute expected vs found line items per period/statement, expose in `/summary`, and surface in the UI so users see gaps.
3. UI ordering & clarity
   - Apply canonical display order in `/statements` responses and add section labels/empty-state hints when coverage is partial.
4. Validation & integrity
   - Add accounting tie checks (A = L + E, CF ties) and fail builds/pipeline steps on violation.
   - Add regression tests for the tag-map to prevent coverage regressions; keep fixture-based assertions for NVDA/AMZN/AAPL parity.
5. Provenance surfacing
   - Ensure `/summary` and `/statements` include source paths/contexts for each number so UI can show audit trail links.

---

## 15. Initial File Creation Rules

Do **not** create implementation files yet.

When approved, first-generation files should be **empty stubs only**:
- config
- canonical schema
- ingestion fetchers
- statement builder
- backtest harness

No logic without tests and provenance hooks.

---

## 16. Definition of Success (MVP)

DeltaIsland Research is successful when:
- Models tie automatically
- Forecasts are reproducible
- Backtests run end-to-end
- Every output explains itself
- The system is boringly honest

Predictions are allowed to be wrong.  
The *process* is not.

---
