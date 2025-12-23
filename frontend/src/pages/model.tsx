import Head from "next/head";
import { useRouter } from "next/router";
import { useState, type FormEvent } from "react";

type ModelValue = {
  value: number | null;
  unit: string | null;
  source?: Record<string, any>;
};

type ModelPeriod = {
  period_end: string;
  values: Record<string, ModelValue>;
  scenario?: string | null;
  period_index?: number | null;
  assumptions?: Record<string, number | null> | null;
};

type ModelStatement = {
  actuals: ModelPeriod[];
  forecast: ModelPeriod[];
};

type ModelResponse = {
  ticker: string;
  as_of?: string | null;
  drivers?: Record<
    string,
    { value: number | null; description?: string | null; sources?: { line_item?: string; period_end?: string; note?: string }[]; is_default?: boolean }
  >;
  scenarios?: string[];
  statements: Record<string, ModelStatement>;
  forecast_summary?: Record<string, Record<string, { point_estimate?: number; low?: number; high?: number }>>;
};

type Props = {
  ticker: string;
  model?: ModelResponse | null;
  actualsLimit: number;
  error?: string | null;
};

const STATEMENT_DISPLAY_ORDER: Record<string, string[]> = {
  income_statement: [
    "revenue",
    "cogs",
    "gross_profit",
    "r_and_d",
    "sga",
    "operating_expenses",
    "operating_income",
    "interest_income",
    "interest_expense",
    "other_income_expense",
    "pre_tax_income",
    "income_tax_expense",
    "net_income",
    "ebitda",
    "total_expenses",
    "eps_basic",
    "eps_diluted",
    "shares_basic",
    "shares_diluted",
    "shares_outstanding",
  ],
  balance_sheet: [
    "cash",
    "short_term_investments",
    "long_term_investments",
    "accounts_receivable",
    "inventory",
    "prepaid_expenses",
    "other_assets_current",
    "assets_current",
    "other_assets_noncurrent",
    "assets_noncurrent",
    "assets",
    "ppe",
    "goodwill",
    "intangible_assets",
    "accounts_payable",
    "accrued_expenses",
    "deferred_revenue_current",
    "deferred_revenue_noncurrent",
    "other_liabilities_current",
    "liabilities_current",
    "other_liabilities_noncurrent",
    "liabilities_noncurrent",
    "liabilities",
    "debt_current",
    "debt_long_term",
    "equity",
    "retained_earnings",
    "treasury_stock",
    "minority_interest",
    "liabilities_equity",
  ],
  cash_flow: [
    "net_income",
    "depreciation_amortization",
    "stock_compensation",
    "change_working_capital",
    "cfo",
    "capex",
    "acquisitions",
    "cfi",
    "dividends_paid",
    "share_repurchases",
    "debt_issued",
    "debt_repaid",
    "cff",
    "fx_on_cash",
    "change_in_restricted_cash",
    "change_in_cash",
    "fcf",
  ],
};

const LABEL_MAP: Record<string, string> = {
  cfo: "Cash Flow From Ops",
  cfi: "Cash Flow From Investing",
  cff: "Cash Flow From Financing",
  fcf: "Free Cash Flow",
  ppe: "Property, Plant & Equipment",
  r_and_d: "R&D",
  sga: "SG&A",
  eps_basic: "EPS (Basic)",
  eps_diluted: "EPS (Diluted)",
  shares_basic: "Shares Outstanding (Basic)",
  shares_diluted: "Shares Outstanding (Diluted)",
};

export async function getServerSideProps(ctx: any) {
  const ticker = (ctx.query.ticker || "AAPL").toString().toUpperCase();
  const apiBase = process.env.API_INTERNAL_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://api:8000";
  const limitParam = Number(ctx.query.actuals_limit);
  const allowedLimits = [2, 4, 6, 8, 12];
  const actualsLimit = allowedLimits.includes(limitParam) ? limitParam : 4;
  let model: ModelResponse | null = null;
  let error: string | undefined;
  try {
    const res = await fetch(`${apiBase}/model/${ticker}?actuals_limit=${actualsLimit}`);
    if (res.ok) {
      model = await res.json();
    } else {
      error = `Model not available (${res.status})`;
    }
  } catch (err: any) {
    error = err?.message || "Failed to load model";
  }
  return { props: { ticker, model, actualsLimit, error: error || null } };
}

function formatCurrency(value: number | null, opts: { withSign?: boolean } = {}) {
  const withSign = opts.withSign !== undefined ? opts.withSign : true;
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  const abs = Math.abs(num);
  let divisor = 1;
  let suffix = "";
  if (abs >= 1_000_000_000_000) {
    divisor = 1_000_000_000_000;
    suffix = "T";
  } else if (abs >= 1_000_000_000) {
    divisor = 1_000_000_000;
    suffix = "B";
  } else if (abs >= 1_000_000) {
    divisor = 1_000_000;
    suffix = "M";
  }
  const scaled = num / divisor;
  const decimals = divisor === 1 ? (abs >= 1 ? 2 : 3) : 3;
  const factor = Math.pow(10, decimals);
  const floored = Math.floor(scaled * factor) / factor;
  const formatted = floored.toLocaleString("en-US", {
    minimumFractionDigits: floored % 1 === 0 ? 0 : Math.min(decimals, 3),
    maximumFractionDigits: decimals,
  });
  const sign = withSign && num < 0 ? "-" : "";
  return `${sign}$${formatted}${suffix}`;
}

function formatPercent(value: number | null) {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  const pct = Math.floor(num * 10000) / 100;
  return `${pct.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function formatDriverValue(key: string, value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const lower = key.toLowerCase();
  if (lower.includes("margin") || lower.includes("growth") || lower.includes("rate") || lower.includes("pct")) {
    return formatPercent(value);
  }
  if (lower.includes("shares")) {
    return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return formatCurrency(value);
}

function formatValue(value: number | null, unit: string | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (unit && unit.toUpperCase() === "SHARES") {
    return Math.round(value).toLocaleString("en-US");
  }
  return formatCurrency(value, { withSign: true });
}

function formatDate(value: string | null | undefined) {
  if (!value) return "n/a";
  return value.split("T")[0];
}

function humanLabel(key: string | null | undefined): string {
  if (!key) return "N/A";
  const lower = key.toLowerCase();
  if (LABEL_MAP[lower]) return LABEL_MAP[lower];
  return lower
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function sortLineItems(statement: string, items: string[]) {
  const order = STATEMENT_DISPLAY_ORDER[statement] || [];
  return items.sort((a, b) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

export default function ModelPage({ ticker, model, actualsLimit, error }: Props) {
  const router = useRouter();
  const [input, setInput] = useState(ticker);
  const scenarios = model?.scenarios && model.scenarios.length > 0 ? model.scenarios : ["base"];
  const [scenario, setScenario] = useState(scenarios[0]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input) return;
    router.push(`/model?ticker=${input.toUpperCase()}&actuals_limit=${actualsLimit}`);
  };

  const drivers = model?.drivers || {};
  const statements = model?.statements || {};

  const handleActualsLimitChange = (value: number) => {
    router.push(`/model?ticker=${ticker}&actuals_limit=${value}`);
  };

  const buildCellTooltip = (
    statement: string,
    lineItem: string,
    period: ModelPeriod,
    value: ModelValue | undefined
  ) => {
    if (!value) return null;
    const source = value.source || {};
    const tooltip = [
      `Statement: ${humanLabel(statement)}`,
      `Line item: ${humanLabel(lineItem)}`,
      `Period: ${period.period_end}`,
    ];
    if (period.scenario) {
      tooltip.push(`Scenario: ${period.scenario.toUpperCase()}`);
    }
    if (period.assumptions) {
      const assumptions = Object.entries(period.assumptions)
        .map(([key, val]) => `${humanLabel(key)}=${formatDriverValue(key, val as number | null)}`)
        .join(", ");
      if (assumptions) tooltip.push(`Assumptions: ${assumptions}`);
    }
    if (source.path) {
      tooltip.push(`Path: ${source.path}`);
    }
    if (source.unit) {
      tooltip.push(`Unit: ${source.unit}`);
    }
    return tooltip.join(" • ");
  };

  return (
    <div className="page">
      <Head>
        <title>{ticker} Model</title>
      </Head>
      <div className="hero">
        <h1>Model</h1>
        <p>Driver-based 3-statement model with scenarios and provenance.</p>
        <form className="ticker-form" onSubmit={handleSubmit}>
          <label htmlFor="ticker">Ticker</label>
          <input id="ticker" value={input} onChange={(e) => setInput(e.target.value)} />
          <button type="submit">Load</button>
          <a className="link" href={`/?ticker=${ticker}`}>
            Back to statements
          </a>
        </form>
      </div>

      {error && <p className="muted">{error}</p>}
      {!model && !error && <p className="muted">No model data available.</p>}

      {model && (
        <>
          <section className="grid">
            <div className="card">
              <div className="card-header">
                <h2>Scenario</h2>
                <span className="pill">Model</span>
              </div>
              <div className="period-selector">
                <label htmlFor="scenario">Scenario</label>
                <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  {scenarios.map((s) => (
                    <option key={s} value={s}>
                      {s.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
              <div className="period-selector">
                <label htmlFor="actuals">Actuals</label>
                <select
                  id="actuals"
                  value={actualsLimit}
                  onChange={(e) => handleActualsLimitChange(Number(e.target.value))}
                >
                  {[2, 4, 6, 8, 12].map((limit) => (
                    <option key={limit} value={limit}>
                      Last {limit}
                    </option>
                  ))}
                </select>
              </div>
              <p className="muted">As-of: {formatDate(model.as_of)}</p>
            </div>
            <div className="card">
              <div className="card-header">
                <h2>Forecast Ranges</h2>
                <span className="pill">Summary</span>
              </div>
              {model.forecast_summary && Object.keys(model.forecast_summary).length > 0 ? (
                <div className="list">
                  {Object.entries(model.forecast_summary).map(([period, metrics]) => (
                    <div key={period} className="statement-period">
                      <div className="statement-header">
                        <h3>{period}</h3>
                      </div>
                      {Object.entries(metrics).map(([metric, vals]) => (
                        <div key={metric} className="model-range">
                          <strong>{humanLabel(metric)}</strong>: {formatCurrency(vals.point_estimate ?? null)}{" "}
                          <span className="muted">
                            ({formatCurrency(vals.low ?? null)} to {formatCurrency(vals.high ?? null)})
                          </span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">No forecast summary available.</p>
              )}
            </div>
          </section>

          <section className="card full">
            <div className="card-header">
              <h2>Drivers</h2>
              <span className="pill">Inputs</span>
            </div>
            {Object.keys(drivers).length === 0 ? (
              <p className="muted">No drivers available.</p>
            ) : (
              <ul className="list">
                {Object.entries(drivers).map(([key, val]) => (
                  <li key={key}>
                    <strong>{humanLabel(key)}</strong>: {formatDriverValue(key, val?.value ?? null)}
                    {val?.description && <div className="muted">{val.description}</div>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card full">
            <div className="card-header">
              <h2>3-Statement Model</h2>
              <span className="pill">Projected</span>
            </div>
            <div className="statement">
              {Object.entries(statements).map(([stmt, payload]) => {
                const actuals = payload.actuals || [];
                const forecast = (payload.forecast || []).filter((p) => (p.scenario || "base") === scenario);
                const columns = [...actuals, ...forecast];
                const lineItemSet = new Set<string>();
                columns.forEach((period) => {
                  Object.keys(period.values || {}).forEach((line) => lineItemSet.add(line));
                });
                const lineItems = sortLineItems(stmt, Array.from(lineItemSet));

                return (
                  <div key={stmt} className="statement-block">
                    <h3>{humanLabel(stmt)}</h3>
                    <div className="table-wrap">
                      <table className="model-table">
                        <thead>
                          <tr>
                            <th>Line item</th>
                            {columns.map((col) => (
                              <th key={`${col.period_end}-${col.scenario || "actual"}`} className={col.scenario ? "model-col-forecast" : "model-col-actual"}>
                                {col.period_end}
                                {col.scenario && <span className="pill model-pill">{col.scenario}</span>}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {lineItems.map((line) => (
                            <tr key={`${stmt}-${line}`}>
                              <td>{humanLabel(line)}</td>
                              {columns.map((col) => {
                                const cellValue = col.values?.[line];
                                const tooltip = buildCellTooltip(stmt, line, col, cellValue);
                                return (
                                  <td
                                    key={`${col.period_end}-${line}`}
                                    className={col.scenario ? "model-col-forecast" : "model-col-actual"}
                                    data-tooltip={tooltip || undefined}
                                    aria-label={tooltip || undefined}
                                  >
                                    {formatValue(cellValue?.value ?? null, cellValue?.unit)}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
