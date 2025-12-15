# Principles

- **Receipts for every number**: each output cell links to source (filing, tag, date) plus transformation steps.
- **Time-travel correctness**: backtests must only use data available as of the forecast date.
- **Deterministic first, ML later**: rules and accounting constraints come before probabilistic models.
- **Sector-aware eventually**: start generic; add industry templates once the MVP is stable.
- **Explicit uncertainty**: show ranges and scenario spreads, not just point estimates.
