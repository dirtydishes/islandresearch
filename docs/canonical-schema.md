# Canonical Schema (expanded)

Canonical facts capture normalized financial statements with explicit period typing, units, and provenance. Extend only when mappings **and** tests exist.

## Statements
- `income_statement` (duration)
- `balance_sheet` (instant)
- `cash_flow` (duration)

## Canonical line items (per statement)

**Income Statement**
- `revenue`, `cogs`, `gross_profit`
- `r_and_d`, `sga`, `operating_expenses`, `operating_income`
- `interest_income`, `interest_expense`, `other_income_expense`, `pre_tax_income`, `income_tax_expense`
- `net_income`, `ebitda`, `total_expenses`
- `eps_basic`, `eps_diluted`, `shares_basic`, `shares_diluted`, `shares_outstanding`

**Balance Sheet**
- `cash`, `short_term_investments`, `accounts_receivable`, `inventory`, `prepaid_expenses`
- `assets_current`, `assets_noncurrent`, `assets`
- `ppe`, `goodwill`, `intangible_assets`
- `accounts_payable`, `accrued_expenses`, `deferred_revenue_current`, `deferred_revenue_noncurrent`
- `liabilities_current`, `liabilities_noncurrent`, `liabilities`
- `debt_current`, `debt_long_term`, `equity`, `retained_earnings`, `treasury_stock`, `minority_interest`, `liabilities_equity`

**Cash Flow**
- `net_income`, `depreciation_amortization`, `stock_compensation`, `change_working_capital`
- `cfo` (operating), `capex`, `acquisitions`, `cfi` (investing)
- `dividends_paid`, `share_repurchases`, `debt_issued`, `debt_repaid`, `cff` (financing)

## Units
- `USD` for monetary values (default)
- `USDPerShare` for EPS
- `SHARES` for share counts

## Period typing
- `duration` for income statement and cash flow rows.
- `instant` for balance sheet rows.
- Unknown rows are rejected.

## Validation rules
- Only allowed statement/line_item pairs are materialized.
- Period_end is required; duration/instant inferred from statement if not provided.
- Units are uppercased and default to `USD` if missing; per-share and share units are preserved.
- Consolidated (no segment) contexts are preferred; statement-specific period types are enforced.

## Mapping + provenance
- A GAAP tag → canonical line-item map drives parsing; multiple GAAP tags may map to the same canonical item with priority rules.
- Provenance keeps `source_path`, `tag`, `contextref`, `unitref`, `period_end`, and `source_fact_id` so every number can be traced.
- Backfill/materialization logic remains deterministic: same input facts → same canonical rows. Extend schema only with accompanying mappings and tests.
