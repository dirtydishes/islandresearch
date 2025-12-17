# Canonical Schema (MVP)

Canonical facts capture normalized financial statements with explicit period typing, units, and provenance. Statements and line items are intentionally small; extend only when mappings and tests exist.

## Statements
- `income_statement` (duration)
- `balance_sheet` (instant)
- `cash_flow` (duration)

## Line items (per statement)
- Income Statement: `revenue`, `gross_profit`, `operating_income`, `pre_tax_income`, `net_income`, `total_expenses`, `cogs`, `r_and_d`, `sga`, `operating_expenses`, `eps_basic`, `eps_diluted`, `shares_basic`, `shares_diluted`, `shares_outstanding`
- Balance Sheet: `assets`, `assets_current`, `liabilities`, `liabilities_current`, `debt_long_term`, `debt_current`, `cash`, `short_term_investments`, `ppe`, `inventory`, `accounts_receivable`, `accounts_payable`, `equity`, `liabilities_equity`
- Cash Flow: `cfo`, `cfi`, `cff`, `capex`, `depreciation_amortization`

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
- Units are uppercased and default to `USD` if missing.

## Coverage notes
- Parser targets a small set of us-gaap tags (revenues, net income, assets/liabilities/equity, cash flow subtotals, capex, D&A, shares) and normalizes scale/decimals.
- Backfill/materialization logic should remain deterministic: same input facts → same canonical rows. Extend schema only with accompanying mappings and tests.
