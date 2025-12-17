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

type Derived = {
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  fcf_margin?: number | null;
  debt_to_equity?: number | null;
  liabilities_to_assets?: number | null;
  eps_basic?: number | null;
  eps_diluted?: number | null;
  fcf?: number | null;
};

type SummaryPeriod = {
  period_end: string;
  values: Record<string, SummaryValue>;
};

type SummaryResponse = {
  ticker: string;
  periods: SummaryPeriod[];
  filings: { accession: string; form: string | null; filed_at: string | null; path: string | null }[];
  covered?: boolean;
  resolvable?: boolean;
  cik?: string | null;
  derived?: Derived;
  drivers?: Record<string, { value: number | null; sources?: { line_item?: string; period_end?: string; note?: string }[] }>;
  forecast?: { period_end: string; values: Record<string, SummaryValue> }[];
  dropped_facts?: number | null;
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
      fetch(`${apiBase}/statements/${ticker}?limit=20`),
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

function formatPercent(value: number | null) {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  const pct = Math.floor(num * 10000) / 100; // floor to 2 decimals
  return `${pct.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function formatUnit(unit: string | null | undefined) {
  if (!unit) return "";
  const upper = unit.toUpperCase();
  if (upper === "USD") return "";
  if (upper === "USDPERSHARE") return "(per share)";
  if (upper === "SHARES") return "(shares)";
  return `(${unit})`;
}

function formatDriverValue(key: string, value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const lower = key.toLowerCase();
  if (lower.includes("margin") || lower.includes("growth")) {
    return formatPercent(value);
  }
  if (lower.includes("shares")) {
    return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return formatCurrency(value);
}

function valueClass(value: number | null | undefined) {
  if (value === null || value === undefined) return "value-neutral";
  if (Number.isNaN(value)) return "value-neutral";
  if (value > 0) return "value-positive";
  if (value < 0) return "value-negative";
  return "value-neutral";
}

function deltaIndicator(current: number | null | undefined, prev: number | null | undefined) {
  if (current === null || current === undefined || prev === null || prev === undefined) return "•";
  if (current > prev) return "↑";
  if (current < prev) return "↓";
  return "•";
}

function deltaClass(diff: number | null | undefined) {
  if (diff === null || diff === undefined) return "delta-neutral";
  if (Number.isNaN(diff)) return "delta-neutral";
  if (diff > 0) return "delta-positive";
  if (diff < 0) return "delta-negative";
  return "delta-neutral";
}

function renderValueWithDelta(
  value: number | null | undefined,
  prev: number | null | undefined,
  formatter: (v: number) => string
) {
  const cls = valueClass(value);
  const arrow = deltaIndicator(value, prev);
  const hasPrev = prev !== null && prev !== undefined && value !== null && value !== undefined;
  const diff = hasPrev ? (value as number) - (prev as number) : null;
  const pct = diff !== null && prev !== 0 && prev !== null && prev !== undefined ? (diff / (prev as number)) * 100 : null;
  const dClass = deltaClass(diff);

  return (
    <span className="value-wrapper">
      <span className={`value ${cls}`}>
        {arrow} {value === null || value === undefined ? "—" : formatter(value)}
      </span>
      <span className={`delta ${dClass}`}>
        {hasPrev
          ? `${diff !== null ? (diff > 0 ? "+" : "") + formatCurrency(diff) : ""}${
              pct !== null ? ` (${pct > 0 ? "+" : ""}${pct.toFixed(2)}%)` : ""
            }`
          : "Δ N/A"}
      </span>
    </span>
  );
}

function buildForecastFromStatements(statements: StatementPeriod[]): { period_end: string; values: Record<string, SummaryValue> } | null {
  if (!statements || statements.length === 0) return null;
  const latest = statements[0];
  const lines = latest.lines || {};
  const findValue = (target: string) => {
    for (const [, arr] of Object.entries(lines)) {
      const hit = arr.find((l) => l.line_item === target);
      if (hit && hit.value !== null && hit.value !== undefined) return hit.value;
    }
    return null;
  };
  const revenue = findValue("revenue");
  if (revenue === null) return null;
  const netIncome = findValue("net_income");
  const grossProfit = findValue("gross_profit");
  const operatingIncome = findValue("operating_income");
  const shares = findValue("shares_diluted") ?? findValue("shares_basic");
  const cfo = findValue("cfo");
  const cfi = findValue("cfi");
  const fcf = cfo !== null && cfi !== null ? (cfo ?? 0) + (cfi ?? 0) : null;

  const nextRevenue = revenue * 1.02;
  const netMargin = revenue ? (netIncome ?? 0) / revenue : 0;
  const grossMargin = revenue ? (grossProfit ?? 0) / revenue : 0;
  const opMargin = revenue ? (operatingIncome ?? 0) / revenue : 0;
  const fcfMargin = revenue && fcf !== null ? fcf / revenue : 0;

  return {
    period_end: `${latest.period_end} +1`,
    values: {
      revenue: { value: nextRevenue, unit: "USD" },
      gross_profit: { value: nextRevenue * grossMargin, unit: "USD" },
      operating_income: { value: nextRevenue * opMargin, unit: "USD" },
      net_income: { value: nextRevenue * netMargin, unit: "USD" },
      eps_diluted: { value: shares ? (nextRevenue * netMargin) / shares : null, unit: "USDPerShare" },
      fcf: { value: nextRevenue * fcfMargin, unit: "USD" },
    },
  };
}

export default function Home({ ticker, statements, summary, error }: Props) {
  const router = useRouter();
  const [input, setInput] = useState(ticker);
  const [triggering, setTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<string | null>(statements[0]?.period_end ?? null);
  const covered = summary?.covered ?? false;
  const resolvable = summary?.resolvable ?? false;
  const derived = summary?.derived || null;
  const drivers = summary?.drivers || null;
  const apiForecast = summary?.forecast && summary.forecast.length > 0 ? summary.forecast[0] : null;
  const latestForecast = apiForecast || buildForecastFromStatements(statements);
  const previousSummary = summary?.periods && summary.periods.length > 1 ? summary.periods[1] : null;
  const periodOptions = statements.map((p) => p.period_end);

  const currentPeriodLines = selectedPeriod
    ? statements.find((p) => p.period_end === selectedPeriod)?.lines ?? {}
    : statements[0]?.lines ?? {};
  const prevPeriod = selectedPeriod
    ? (() => {
        const idx = statements.findIndex((p) => p.period_end === selectedPeriod);
        return idx >= 0 && idx + 1 < statements.length ? statements[idx + 1] : null;
      })()
    : statements[1] ?? null;

  const apiBaseClient = () => process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const buildSourceUrl = (path: string | null | undefined) => {
    if (!path) return null;
    const base = apiBaseClient().replace(/\/$/, "");
    return `${base}/artifact?path=${encodeURIComponent(path)}`;
  };

  const handlePeriodChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelectedPeriod(val);
  };

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
        let message = `Trigger failed (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail) {
            message = body.detail;
          }
        } catch (_) {
          // ignore json parse error
        }
        setTriggerError(message);
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
          <div className="coverage-row">
            <span className={`pill ${covered ? "success" : resolvable ? "warn" : "danger"}`}>
              {covered ? "Covered by IR" : resolvable ? "SEC lookup only (not covered)" : "Ticker not found in SEC list"}
            </span>
            {summary?.cik && <span className="muted">CIK {summary.cik}</span>}
          </div>
          {error && <p className="muted">API error: {error}</p>}
          {triggerError && <p className="muted">Trigger error: {triggerError}</p>}
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
                    <span>{humanLabel(key)}</span>
                    {renderValueWithDelta(
                      val.value,
                      previousSummary?.values?.[key]?.value ?? null,
                      (v) => `${formatCurrency(v)} ${formatUnit(val.unit)}`
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Derived</h2>
              <span className="pill">Ratios</span>
            </div>
            {!derived ? (
              <p className="muted">No derived metrics yet.</p>
            ) : (
              <ul className="kv">
                <li>
                  <span>Gross Margin</span>
                  {renderValueWithDelta(
                    derived.gross_margin ?? null,
                    previousSummary?.values?.gross_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Operating Margin</span>
                  {renderValueWithDelta(
                    derived.operating_margin ?? null,
                    previousSummary?.values?.operating_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Net Margin</span>
                  {renderValueWithDelta(
                    derived.net_margin ?? null,
                    previousSummary?.values?.net_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>FCF Margin</span>
                  {renderValueWithDelta(
                    derived.fcf_margin ?? null,
                    previousSummary?.values?.fcf_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Debt / Equity</span>
                  {renderValueWithDelta(
                    derived.debt_to_equity ?? null,
                    previousSummary?.values?.debt_to_equity?.value ?? null,
                    (v) => v.toFixed(2)
                  )}
                </li>
                <li>
                  <span>Liabilities / Assets</span>
                  {renderValueWithDelta(
                    derived.liabilities_to_assets ?? null,
                    previousSummary?.values?.liabilities_to_assets?.value ?? null,
                    (v) => v.toFixed(2)
                  )}
                </li>
                <li>
                  <span>EPS (Diluted)</span>
                  {renderValueWithDelta(
                    derived.eps_diluted ?? null,
                    previousSummary?.values?.eps_diluted?.value ?? null,
                    formatCurrency
                  )}
                </li>
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
                    {f.path && (
                      <div className="muted">
                        <a className="link" href={buildSourceUrl(f.path) ?? undefined} target="_blank" rel="noreferrer">
                          Source
                        </a>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <h2>Simple Forecast</h2>
              <span className="pill">T+1</span>
            </div>
              {!latestForecast ? (
                <p className="muted">No forecast yet. Ingest data first.</p>
              ) : (
                <ul className="kv">
                  {Object.entries(latestForecast.values).map(([key, val]) => {
                    const label = humanLabel(key);
                    return (
                      <li key={key}>
                        <span>{label}</span>
                        {renderValueWithDelta(
                          val.value,
                          null,
                          (v) => `${key.includes("margin") ? formatPercent(v) : formatCurrency(v)} ${formatUnit(val.unit)}`
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
                  <div className="card">
                    <div className="card-header">
                      <h2>Drivers & Provenance</h2>
                      <span className="pill">Assumptions</span>
                    </div>
                    {!drivers || Object.keys(drivers).length === 0 ? (
                      <p className="muted">No drivers available.</p>
                    ) : (
                      <ul className="list">
                {Object.entries(drivers).map(([key, val]) => (
                  <li key={key}>
                    <strong>{humanLabel(key)}</strong>:{" "}
                    {renderValueWithDelta(val.value, null, (v) => formatDriverValue(key, v))}
                    {val.sources && val.sources.length > 0 && (
                      <div className="muted">
                        Sources:{" "}
                        {val.sources
                          .filter((s) => s.period_end || s.line_item)
                          .map((s) => `${humanLabel(s.line_item || "line")} @ ${s.period_end || "n/a"}${s.note ? ` (${s.note})` : ""}`)
                          .join(", ")}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
        <section className="grid">
          <div className="card">
            <h2>Ingestion</h2>
            <p>EDGAR-first pipeline for filings, XBRL facts, and raw artifacts.</p>
            {summary?.dropped_facts != null && (
              <p className="muted">Dropped facts (disallowed): {summary.dropped_facts}</p>
            )}
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
          <div className="period-selector">
            <label htmlFor="period">Period</label>
            <select id="period" value={selectedPeriod ?? ""} onChange={handlePeriodChange}>
              {periodOptions.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          {statements.length === 0 ? (
            <p className="muted">No statements for {ticker}. Ingest and parse first.</p>
          ) : (
            <div className="statement">
              {Object.entries(currentPeriodLines).map(([stmt, items]) => (
                <div key={stmt} className="statement-block">
                  <h3>{humanLabel(stmt)}</h3>
                  <ul>
                    {items.map((item) => (
                      <li key={`${stmt}-${item.line_item}`}>
                        <span>
                          {humanLabel(item.line_item)}{" "}
                          {summary?.drivers?.[item.line_item ?? ""]?.sources && (
                            <em className="muted">
                              ({summary.drivers[item.line_item ?? ""]?.sources?.map((s) => s.period_end).join(", ")})
                            </em>
                          )}
                        </span>
                        {renderValueWithDelta(
                          item.value,
                          (() => {
                            if (!prevPeriod) return null;
                            const prevLines = prevPeriod.lines[stmt] || [];
                            const hit = prevLines.find((l) => l.line_item === item.line_item);
                            return hit?.value ?? null;
                          })(),
                          formatCurrency
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  );
}

const LABEL_MAP: Record<string, string> = {
  cogs: "COGS",
  eps_basic: "EPS (Basic)",
  eps_diluted: "EPS (Diluted)",
  net_income: "Net Income",
  gross_profit: "Gross Profit",
  operating_income: "Operating Income",
  operating_expenses: "Operating Expenses",
  r_and_d: "R&D",
  sga: "SG&A",
  shares_basic: "Shares Outstanding (Basic)",
  shares_diluted: "Shares Outstanding (Diluted)",
};

function humanLabel(key: string | null | undefined): string {
  if (!key) return "N/A";
  const lower = key.toLowerCase();
  if (LABEL_MAP[lower]) return LABEL_MAP[lower];
  return lower
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
