import Head from "next/head";
import { useRouter } from "next/router";
import { useState } from "react";

type StatementLine = {
  line_item: string | null;
  value: number | null;
  unit: string | null;
};

type StatementPeriod = {
  period_end: string;
  lines: Record<string, StatementLine[]>;
};

type SummaryValue = {
  value: number | null;
  unit: string | null;
};

type SummaryPeriod = {
  period_end: string;
  values: Record<string, SummaryValue>;
};

type SummaryResponse = {
  ticker: string;
  periods: SummaryPeriod[];
  filings: { accession: string; form: string | null; filed_at: string | null; path: string | null }[];
};

type Props = {
  ticker: string;
  statements: StatementPeriod[];
  summary?: SummaryResponse | null;
  error?: string;
};

export async function getServerSideProps(ctx: any) {
  const ticker = (ctx.query.ticker || "AAPL").toString().toUpperCase();
  const apiBase = process.env.API_INTERNAL_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://api:8000";
  let statements: StatementPeriod[] = [];
  let summary: SummaryResponse | null = null;
  let error: string | undefined;
  try {
    const [stmtRes, summaryRes] = await Promise.all([
      fetch(`${apiBase}/statements/${ticker}`),
      fetch(`${apiBase}/summary/${ticker}`),
    ]);
    const stmtJson = stmtRes.ok ? await stmtRes.json() : { periods: [] };
    statements = stmtJson.periods ?? [];
    if (summaryRes.ok) {
      summary = await summaryRes.json();
    } else {
      summary = null;
    }
  } catch (err: any) {
    error = err?.message || "Failed to load statements";
  }
  return { props: { ticker, statements, summary, error: error || null } };
}

function formatCurrency(value: number | null) {
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
  // Floor to avoid overstating; use up to 3 decimals for large numbers, 2 for smaller.
  const decimals = divisor === 1 ? (abs >= 1 ? 2 : 3) : 3;
  const factor = Math.pow(10, decimals);
  const floored = Math.floor(scaled * factor) / factor;
  const formatted = floored.toLocaleString("en-US", {
    minimumFractionDigits: floored % 1 === 0 ? 0 : Math.min(decimals, 3),
    maximumFractionDigits: decimals,
  });
  return `$${formatted}${suffix}`;
}

function formatUnit(unit: string | null | undefined) {
  if (!unit) return "";
  const upper = unit.toUpperCase();
  if (upper === "USD") return "";
  if (upper === "USDPERSHARE") return "(per share)";
  if (upper === "SHARES") return "(shares)";
  return `(${unit})`;
}

export default function Home({ ticker, statements, summary, error }: Props) {
  const router = useRouter();
  const [input, setInput] = useState(ticker);
  const [triggering, setTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const apiBaseClient = () => process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const nextTicker = input.trim().toUpperCase() || "AAPL";
    router.push(`/?ticker=${nextTicker}`);
  };

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerError(null);
    try {
      const base = apiBaseClient();
      const res = await fetch(`${base}/trigger/${input.trim().toUpperCase() || ticker}`, { method: "POST" });
      if (!res.ok) {
        setTriggerError(`Trigger failed (${res.status})`);
      } else {
        setTriggerError(null);
        // Force reload to pick up new data after jobs complete.
        router.replace(`/?ticker=${input.trim().toUpperCase() || ticker}`);
      }
    } catch (err: any) {
      setTriggerError(err?.message || "Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  return (
    <>
      <Head>
        <title>deltaisland research</title>
      </Head>
      <main className="page">
        <section className="hero">
          <h1>deltaisland research</h1>
          <p>Public-filings driven forecasts with audit-ready lineage.</p>
          <form className="ticker-form" onSubmit={handleSubmit}>
            <label htmlFor="ticker">Ticker</label>
            <input
              id="ticker"
              name="ticker"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="AAPL"
            />
            <button type="submit">Load</button>
            <a className="link" href="/mock">
              View mock demo
            </a>
            <button type="button" className="ghost" onClick={handleTrigger} disabled={triggering}>
              {triggering ? "Running…" : "Ingest & Parse"}
            </button>
          </form>
          {error && <p className="muted">API error: {error}</p>}
          {triggerError && <p className="muted">Trigger error: {triggerError}</p>}
        </section>
        <section className="grid">
          <div className="card">
            <h2>Ingestion</h2>
            <p>EDGAR-first pipeline for filings, XBRL facts, and raw artifacts.</p>
          </div>
          <div className="card">
            <h2>Model</h2>
            <p>Driver-based 3-statement forecast with valuation and scenarios.</p>
          </div>
          <div className="card">
            <h2>Audit Trail</h2>
            <p>Receipts for every number: source links and transformation steps.</p>
          </div>
        </section>
        <section className="card full">
          <div className="card-header">
            <h2>Statements</h2>
            <span className="pill">Canonical</span>
          </div>
          {statements.length === 0 ? (
            <p className="muted">No statements for {ticker}. Ingest and parse first.</p>
          ) : (
            statements.map((period) => (
              <div key={period.period_end} className="statement-period">
                <div className="statement-header">
                  <h3>{period.period_end}</h3>
                </div>
                <div className="statement">
                  {Object.entries(period.lines).map(([stmt, items]) => (
                    <div key={stmt} className="statement-block">
                      <h3>{stmt}</h3>
                      <ul>
                        {items.map((item) => (
                          <li key={`${stmt}-${item.line_item}`}>
                            <span>{item.line_item ?? "n/a"}</span>
                            <strong>{formatCurrency(item.value)}</strong>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </section>
        <section className="grid">
          <div className="card">
            <div className="card-header">
              <h2>Key Metrics</h2>
              <span className="pill">Latest</span>
            </div>
            {!summary || summary.periods.length === 0 ? (
              <p className="muted">No metrics available. Ingest and parse first.</p>
            ) : (
              <ul className="kv">
                {Object.entries(summary.periods[0].values).map(([key, val]) => (
                  <li key={key}>
                    <span>{key}</span>
                    <strong>
                      {formatCurrency(val.value)} {formatUnit(val.unit)}
                    </strong>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Filings</h2>
              <span className="pill">Latest</span>
            </div>
            {!summary || summary.filings.length === 0 ? (
              <p className="muted">No filings saved.</p>
            ) : (
              <ul className="list">
                {summary.filings.map((f) => (
                  <li key={f.accession}>
                    <div>
                      <strong>{f.form || "form"}</strong> — {f.accession}
                    </div>
                    <div className="muted">Filed: {f.filed_at || "n/a"}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
