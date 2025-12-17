import Head from "next/head";

type StatementRow = {
  period: string;
  revenue: number;
  ebitda: number;
  net_income: number;
  cash: number;
  debt: number;
  fcf?: number;
};

type Valuation = {
  enterprise_value: number;
  equity_value: number;
  shares_outstanding: number;
  implied_share_price: number;
  notes: string;
};

type MockModel = {
  company: string;
  as_of: string;
  statements: StatementRow[];
  forecast: StatementRow[];
  valuation: Valuation;
  audit_summary: string[];
};

type Props = {
  data: MockModel;
  statements?: StatementPeriod[];
};

const fallbackData: MockModel = {
  company: "deltaisland research demo (offline)",
  as_of: "N/A",
  statements: [],
  forecast: [],
  valuation: {
    enterprise_value: 0,
    equity_value: 0,
    shares_outstanding: 0,
    implied_share_price: 0,
    notes: "API unavailable; showing empty state.",
  },
  audit_summary: [],
};

type StatementLine = {
  line_item: string | null;
  value: number | null;
  unit: string | null;
};

type StatementPeriod = {
  period_end: string;
  lines: Record<string, StatementLine[]>;
};

export async function getServerSideProps() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  try {
    const [modelRes, statementsRes] = await Promise.all([
      fetch(`${apiBase}/mock/model`),
      fetch(`${apiBase}/statements/AAPL`),
    ]);
    if (!modelRes.ok) throw new Error(`API returned ${modelRes.status}`);
    const data = (await modelRes.json()) as MockModel;
    const stmtData = statementsRes.ok ? await statementsRes.json() : { periods: [] };
    return { props: { data, statements: stmtData.periods ?? [] } };
  } catch (err) {
    return { props: { data: fallbackData, statements: [] } };
  }
}

function formatCurrency(value: number) {
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
  return `$${formatted}${suffix}`;
}

function valueClass(value: number | null | undefined) {
  if (value === null || value === undefined) return "value-neutral";
  if (value > 0) return "value-positive";
  if (value < 0) return "value-negative";
  return "value-neutral";
}

function valueIndicator(value: number | null | undefined) {
  if (value === null || value === undefined) return "•";
  if (value > 0) return "↑";
  if (value < 0) return "↓";
  return "•";
}

function renderValue(value: number | null | undefined, formatter: (v: number) => string) {
  const cls = valueClass(value);
  const indicator = valueIndicator(value);
  return (
    <span className={`value ${cls}`}>
      {indicator} {value === null || value === undefined ? "—" : formatter(value)}
    </span>
  );
}

function renderStatement(lines: Record<string, StatementLine[]> | undefined) {
  if (!lines) return null;
  return (
    <div className="statement">
      {Object.entries(lines).map(([stmt, items]) => (
        <div key={stmt} className="statement-block">
          <h3>{stmt}</h3>
          <ul>
            {items.map((item) => (
              <li key={`${stmt}-${item.line_item}`}>
                <span>{item.line_item ?? "n/a"}</span>
                {renderValue(item.value, formatCurrency)}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function MockPage({ data, statements = [] }: Props) {
  return (
    <>
      <Head>
        <title>deltaisland research mock</title>
      </Head>
      <main className="page">
        <section className="hero">
          <p className="eyebrow">Prototype</p>
          <h1>{data.company}</h1>
          <p>As of {data.as_of}</p>
        </section>
        <section className="grid">
          <div className="card">
            <div className="card-header">
              <h2>Historical</h2>
              <span className="pill">IS/BS</span>
            </div>
            {data.statements.length === 0 ? (
              <p className="muted">No data available.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Revenue</th>
                      <th>EBITDA</th>
                      <th>Net Inc.</th>
                      <th>Cash</th>
                      <th>Debt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.statements.map((row) => (
                      <tr key={row.period}>
                        <td>{row.period}</td>
                        <td>{renderValue(row.revenue, formatCurrency)}</td>
                        <td>{renderValue(row.ebitda, formatCurrency)}</td>
                        <td>{renderValue(row.net_income, formatCurrency)}</td>
                        <td>{renderValue(row.cash, formatCurrency)}</td>
                        <td>{renderValue(row.debt, formatCurrency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Forecast</h2>
              <span className="pill">Scenarios</span>
            </div>
            {data.forecast.length === 0 ? (
              <p className="muted">No data available.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Revenue</th>
                      <th>EBITDA</th>
                      <th>Net Inc.</th>
                      <th>Cash</th>
                      <th>Debt</th>
                      <th>FCF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.forecast.map((row) => (
                      <tr key={row.period}>
                        <td>{row.period}</td>
                        <td>{renderValue(row.revenue, formatCurrency)}</td>
                        <td>{renderValue(row.ebitda, formatCurrency)}</td>
                        <td>{renderValue(row.net_income, formatCurrency)}</td>
                        <td>{renderValue(row.cash, formatCurrency)}</td>
                        <td>{renderValue(row.debt, formatCurrency)}</td>
                        <td>{renderValue(row.fcf ?? null, formatCurrency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Valuation</h2>
              <span className="pill">Base</span>
            </div>
            <ul className="kv">
              <li>
                <span>Enterprise Value</span>
                {renderValue(data.valuation.enterprise_value, formatCurrency)}
              </li>
              <li>
                <span>Equity Value</span>
                {renderValue(data.valuation.equity_value, formatCurrency)}
              </li>
              <li>
                <span>Shares Out</span>
                {renderValue(data.valuation.shares_outstanding, (v) => `${v.toFixed(1)}m`)}
              </li>
              <li>
                <span>Implied Price</span>
                {renderValue(data.valuation.implied_share_price, (v) => `$${v.toFixed(2)}`)}
              </li>
            </ul>
            <p className="muted">{data.valuation.notes}</p>
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Audit Trail</h2>
              <span className="pill">Notes</span>
            </div>
            {data.audit_summary.length === 0 ? (
              <p className="muted">Pending ingestion.</p>
            ) : (
              <ul className="list">
                {data.audit_summary.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="card full">
            <div className="card-header">
              <h2>Statements</h2>
              <span className="pill">Canonical</span>
            </div>
            {statements.length === 0 ? (
              <p className="muted">No canonical statements available.</p>
            ) : (
              statements.map((period) => (
                <div key={period.period_end} className="statement-period">
                  <div className="statement-header">
                    <h3>{period.period_end}</h3>
                  </div>
                  {renderStatement(period.lines)}
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </>
  );
}
