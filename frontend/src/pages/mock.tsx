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

export async function getServerSideProps() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  try {
    const res = await fetch(`${apiBase}/mock/model`);
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const data = (await res.json()) as MockModel;
    return { props: { data } };
  } catch (err) {
    return { props: { data: fallbackData } };
  }
}

function formatCurrency(value: number) {
  return `$${value.toFixed(1)}m`;
}

export default function MockPage({ data }: Props) {
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
                      <td>{formatCurrency(row.revenue)}</td>
                      <td>{formatCurrency(row.ebitda)}</td>
                      <td>{formatCurrency(row.net_income)}</td>
                      <td>{formatCurrency(row.cash)}</td>
                      <td>{formatCurrency(row.debt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                      <td>{formatCurrency(row.revenue)}</td>
                      <td>{formatCurrency(row.ebitda)}</td>
                      <td>{formatCurrency(row.net_income)}</td>
                      <td>{formatCurrency(row.cash)}</td>
                      <td>{formatCurrency(row.debt)}</td>
                      <td>{row.fcf !== undefined ? formatCurrency(row.fcf) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                <strong>{formatCurrency(data.valuation.enterprise_value)}</strong>
              </li>
              <li>
                <span>Equity Value</span>
                <strong>{formatCurrency(data.valuation.equity_value)}</strong>
              </li>
              <li>
                <span>Shares Out</span>
                <strong>{data.valuation.shares_outstanding.toFixed(1)}m</strong>
              </li>
              <li>
                <span>Implied Price</span>
                <strong>${data.valuation.implied_share_price.toFixed(2)}</strong>
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
        </section>
      </main>
    </>
  );
}
