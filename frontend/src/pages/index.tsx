import Head from "next/head";
import { useRouter } from "next/router";
import { useState } from "react";

type StatementLine = {
  line_item: string | null;
  value: number | null;
  unit: string | null;
  source_accession?: string | null;
  source_path?: string | null;
  source_form?: string | null;
  source_filed_at?: string | null;
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
  sources?: Record<
    string,
    { line_item?: string | null; period_end?: string | null; statement?: string | null; unit?: string | null; path?: string | null }
  >;
};

type SummaryResponse = {
  ticker: string;
  periods: SummaryPeriod[];
  filings: { accession: string; form: string | null; filed_at: string | null; path: string | null }[];
  covered?: boolean;
  resolvable?: boolean;
  cik?: string | null;
  derived?: Derived;
  drivers?: Record<
    string,
    {
      value: number | null;
      description?: string | null;
      sources?: { line_item?: string; period_end?: string; note?: string }[];
      is_default?: boolean;
    }
  >;
  forecast?: { period_end: string; values: Record<string, SummaryValue>; scenario?: string | null; period_index?: number | null }[];
  dropped_facts?: number | null;
  coverage?: Record<
    string,
    {
      period_end: string;
      total_found: number;
      total_expected: number;
      by_statement: Record<string, { found: number; expected: number }>;
      missing?: Record<string, string[]>;
    }
  >;
  ties?: Record<string, { period_end: string; bs_tie: number | null; cf_sum: number | null; cash_delta: number | null; cf_tie: number | null }>;
  backtest?: { mae: number; mape: number; directional_accuracy: number; interval_coverage: number; samples?: number };
  backtest_time_travel?: { mae: number; mape: number; directional_accuracy: number; interval_coverage: number; samples?: number };
};

type Props = {
  ticker: string;
  statements: StatementPeriod[];
  summary?: SummaryResponse | null;
  error?: string;
};

export async function getServerSideProps(ctx: any) {
  const ticker = (ctx.query.ticker || "AAPL").toString().toUpperCase();
  // Prefer the internal API host for SSR (works in Docker); fall back to public base or api hostname.
  const apiBase = process.env.API_INTERNAL_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://api:8000";
  let statements: StatementPeriod[] = [];
  let summary: SummaryResponse | null = null;
  let error: string | undefined;
  try {
    const [stmtRes, summaryRes] = await Promise.all([
      fetch(`${apiBase}/statements/${ticker}?limit=12`),
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
  // Floor to avoid overstating; use up to 3 decimals for large numbers, 2 for smaller.
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
  const pct = Math.floor(num * 10000) / 100; // floor to 2 decimals
  return `${pct.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function toneForCoverage(value: number | null) {
  if (value === null || value === undefined) return null;
  if (value >= 0.9) return "success";
  if (value >= 0.75) return "warn";
  return "danger";
}

function toneForDirectionalAccuracy(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (value >= 0.6) return "success";
  if (value >= 0.5) return "warn";
  return "danger";
}

function formatUnit(unit: string | null | undefined) {
  if (!unit) return "";
  const upper = unit.toUpperCase();
  if (upper === "USD") return "";
  if (upper === "USDPERSHARE") return "(per share)";
  if (upper === "SHARES") return "(shares)";
  return `(${unit})`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "n/a";
  return value.split("T")[0];
}

function formatForm(value: string | null | undefined) {
  if (!value) return "Filing";
  return value.toUpperCase();
}

function periodLabelForForm(form: string | null | undefined) {
  if (!form) return "Period end";
  const upper = form.toUpperCase();
  if (upper.startsWith("10-K")) return "FY";
  if (upper.startsWith("10-Q")) return "Q";
  return "Period end";
}

function buildSourceLabel(ticker: string, form: string | null | undefined, periodEnd: string | null | undefined) {
  const label = periodLabelForForm(form);
  const period = periodEnd ? formatDate(periodEnd) : "n/a";
  return `${ticker} ${formatForm(form)} (${label} ${period})`;
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
          ? (() => {
              const diffDisplay =
                diff === null
                  ? ""
                  : `${diff > 0 ? "+" : "-"}${formatCurrency(Math.abs(diff), { withSign: false })}`;
              const pctDisplay =
                pct !== null ? ` (${pct > 0 ? "+" : ""}${pct.toFixed(2)}%)` : "";
              return `${diffDisplay}${pctDisplay}`;
            })()
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
  const backtest = summary?.backtest;
  const forecastAllowed =
    !backtest || Number.isNaN(backtest.directional_accuracy) || backtest.directional_accuracy >= 0.5 ? true : false;
  const previousSummary = summary?.periods && summary.periods.length > 1 ? summary.periods[1] : null;
  const prevSummaryValues = previousSummary?.values || null;
  const periodOptions = statements.map((p) => p.period_end);

  const currentPeriodKey = selectedPeriod ?? statements[0]?.period_end ?? null;
  const currentPeriodLines = selectedPeriod
    ? statements.find((p) => p.period_end === selectedPeriod)?.lines ?? {}
    : statements[0]?.lines ?? {};
  const prevPeriod = selectedPeriod
    ? (() => {
        const idx = statements.findIndex((p) => p.period_end === selectedPeriod);
        return idx >= 0 && idx + 1 < statements.length ? statements[idx + 1] : null;
      })()
    : statements[1] ?? null;
  const currentSummary = summary?.periods?.find((p) => p.period_end === (selectedPeriod ?? statements[0]?.period_end));
  const currentSummarySources = currentSummary?.sources || {};
  const currentCoverage = currentPeriodKey ? summary?.coverage?.[currentPeriodKey] : null;
  const currentMissing = currentCoverage?.missing ?? null;
  const coveragePct =
    currentCoverage && currentCoverage.total_expected
      ? currentCoverage.total_found / currentCoverage.total_expected
      : null;
  const coveragePercentLabel = coveragePct === null ? "—" : formatPercent(coveragePct);
  const coverageTone = toneForCoverage(coveragePct);
  const coverageToneClass = coverageTone ? ` ${coverageTone}` : "";
  const missingTotal = currentMissing
    ? Object.values(currentMissing).reduce((sum, items) => sum + (items?.length ?? 0), 0)
    : 0;
  const missingOrder = ["income_statement", "balance_sheet", "cash_flow"];
  const currentTies = currentPeriodKey ? summary?.ties?.[currentPeriodKey] : null;
  const prevSummary = summary?.periods && summary.periods.length > 1 ? summary.periods[1] : null;
  const timeTravel = summary?.backtest_time_travel || null;
  const daTone = toneForDirectionalAccuracy(timeTravel?.directional_accuracy);
  const daToneClass = daTone ? ` ${daTone}` : "";
  const showQuality = Boolean(currentCoverage || currentTies || timeTravel);
  const hasDrivers = Boolean(drivers && Object.keys(drivers).length > 0);
  const driverPeriodCount = summary?.periods?.length ?? 0;
  const driverWindow = driverPeriodCount ? Math.min(driverPeriodCount, 4) : 0;
  const driverAsOf = summary?.periods?.[0]?.period_end ?? null;
  const forecastPeriods = summary?.forecast ? new Set(summary.forecast.map((f) => f.period_end)) : null;
  const forecastHorizon = forecastPeriods ? forecastPeriods.size : 0;
  const driverForecastNote = forecastHorizon
    ? `Used to project next ${forecastHorizon} period${forecastHorizon === 1 ? "" : "s"}`
    : "Used as base-case inputs for forecasts";
  const driverContext = [
    "Derived from historical actuals (not predictions)",
    driverAsOf ? `As of ${driverAsOf}` : null,
    driverWindow
      ? `Window: last ${driverWindow} period${driverWindow === 1 ? "" : "s"}`
      : "Window: last up to 4 periods",
    driverForecastNote,
  ]
    .filter((part): part is string => Boolean(part))
    .join(" • ");

  const apiBaseClient = () => process.env.NEXT_PUBLIC_API_BASE || "/api";
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
      const ingestLimit = 12;
      const res = await fetch(
        `${base}/trigger/${input.trim().toUpperCase() || ticker}?limit=${ingestLimit}`,
        { method: "POST" }
      );
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
                    prevSummaryValues?.gross_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Operating Margin</span>
                  {renderValueWithDelta(
                    derived.operating_margin ?? null,
                    prevSummaryValues?.operating_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Net Margin</span>
                  {renderValueWithDelta(
                    derived.net_margin ?? null,
                    prevSummaryValues?.net_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>FCF Margin</span>
                  {renderValueWithDelta(
                    derived.fcf_margin ?? null,
                    prevSummaryValues?.fcf_margin?.value ?? null,
                    formatPercent
                  )}
                </li>
                <li>
                  <span>Debt / Equity</span>
                  {renderValueWithDelta(
                    derived.debt_to_equity ?? null,
                    prevSummaryValues?.debt_to_equity?.value ?? null,
                    (v) => v.toFixed(2)
                  )}
                </li>
                <li>
                  <span>Liabilities / Assets</span>
                  {renderValueWithDelta(
                    derived.liabilities_to_assets ?? null,
                    prevSummaryValues?.liabilities_to_assets?.value ?? null,
                    (v) => v.toFixed(2)
                  )}
                </li>
                <li>
                  <span>EPS (Diluted)</span>
                  {renderValueWithDelta(
                    derived.eps_diluted ?? null,
                    prevSummaryValues?.eps_diluted?.value ?? null,
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
              {!forecastAllowed && (
                <p className="muted">Forecast hidden until backtest quality is acceptable (directional accuracy &gt;= 50%).</p>
              )}
              {forecastAllowed && !latestForecast ? (
                <p className="muted">No forecast yet. Ingest data first.</p>
              ) : null}
              {forecastAllowed && latestForecast && (
                <>
                  <ul className="kv">
                    {Object.entries(latestForecast.values).map(([key, val]) => {
                      const label = humanLabel(key);
                      const prevVal =
                        currentSummary?.values?.[key]?.value ??
                        previousSummary?.values?.[key]?.value ??
                        null;
                      const formatter = (v: number) =>
                        `${key.includes("margin") ? formatPercent(v) : formatCurrency(v)} ${formatUnit(val.unit)}`;
                      return (
                        <li key={key}>
                          <span>{label}</span>
                          {renderValueWithDelta(val.value, prevVal, formatter)}
                        </li>
                      );
                    })}
                  </ul>
                  {backtest && (
                    <div className="muted">
                      Backtest: MAE {formatCurrency(backtest.mae || 0)} | DA{" "}
                      {Number.isNaN(backtest.directional_accuracy)
                        ? "N/A"
                        : `${(backtest.directional_accuracy * 100).toFixed(0)}%`}{" "}
                      {backtest.samples ? `(n=${backtest.samples})` : ""}
                    </div>
                  )}
                </>
              )}
            </div>
                  <div className="card">
                    <div className="card-header">
                      <h2>Forecast Inputs</h2>
                      <span className="pill">Historical</span>
                    </div>
                    {hasDrivers && driverContext && <p className="muted">{driverContext}</p>}
                    {!hasDrivers ? (
                      <p className="muted">No drivers available.</p>
                    ) : (
                      <ul className="list">
                {Object.entries(drivers).map(([key, val]) => (
                  <li key={key}>
                    <strong>{humanLabel(key)}</strong>:{" "}
                    {renderValueWithDelta(
                      val.value,
                      previousSummary?.values?.[key]?.value ?? null,
                      (v) => formatDriverValue(key, v)
                    )}
                    {val?.is_default && (
                      <>
                        {" "}
                        <span
                          className="pill warn"
                          data-tooltip="Fallback default used (insufficient data)."
                          aria-label="Fallback default used (insufficient data)."
                        >
                          Defaulted
                        </span>
                      </>
                    )}
                    {val?.description && <div className="muted">{val.description}</div>}
                    {val.sources && val.sources.length > 0 && (
                      <div className="muted">
                        Source periods (history):{" "}
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
            <a className="link" href={`/model?ticker=${ticker}`}>
              Open model view
            </a>
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
            <label htmlFor="period">Period end</label>
            <select id="period" value={selectedPeriod ?? ""} onChange={handlePeriodChange}>
              {periodOptions.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <span className="muted period-hint">Fiscal period end date.</span>
          </div>
          {showQuality && (
            <div className="quality-grid">
              <div className="quality-card">
                <div className="quality-header">
                  <h3 className="quality-title">Coverage</h3>
                  <span
                    className="pill"
                    data-tooltip="Share of mapped line items found for the selected period."
                    aria-label="Share of mapped line items found for the selected period."
                  >
                    Actuals
                  </span>
                </div>
                {currentCoverage ? (
                  <>
                    <div className="coverage-hero">
                      <div>
                        <div className="coverage-total">
                          {currentCoverage.total_found}/{currentCoverage.total_expected}
                        </div>
                        <div className="muted">Line items covered</div>
                      </div>
                      <div className={`coverage-percent${coverageToneClass}`}>{coveragePercentLabel}</div>
                    </div>
                    <div className="coverage-bar">
                      <div
                        className={`coverage-fill${coverageToneClass}`}
                        style={{ width: coveragePct !== null ? `${coveragePct * 100}%` : "0%" }}
                      />
                    </div>
                    <div className="coverage-stats">
                      <div className="metric-item">
                        <div className="metric-label">Income Statement</div>
                        <div className="metric-value">
                          {currentCoverage.by_statement?.income_statement?.found ?? 0}/
                          {currentCoverage.by_statement?.income_statement?.expected ?? 0}
                        </div>
                      </div>
                      <div className="metric-item">
                        <div className="metric-label">Balance Sheet</div>
                        <div className="metric-value">
                          {currentCoverage.by_statement?.balance_sheet?.found ?? 0}/
                          {currentCoverage.by_statement?.balance_sheet?.expected ?? 0}
                        </div>
                      </div>
                      <div className="metric-item">
                        <div className="metric-label">Cash Flow</div>
                        <div className="metric-value">
                          {currentCoverage.by_statement?.cash_flow?.found ?? 0}/
                          {currentCoverage.by_statement?.cash_flow?.expected ?? 0}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="muted">Coverage not available.</p>
                )}
              </div>
              <div className="quality-card">
                <div className="quality-header">
                  <h3 className="quality-title">Missing Items</h3>
                  <span
                    className={`pill ${missingTotal ? "warn" : "success"}`}
                    data-tooltip="Count of mapped line items not found in the selected period."
                    aria-label="Count of mapped line items not found in the selected period."
                  >
                    {missingTotal}
                  </span>
                </div>
                {currentCoverage?.missing ? (
                  <details className="missing-panel">
                    <summary>
                      <span>View missing line items</span>
                      <span className={`pill ${missingTotal ? "warn" : "success"}`}>{missingTotal}</span>
                    </summary>
                    <p className="muted missing-hint">Based on mapped line items in this filing.</p>
                    {missingTotal === 0 ? (
                      <p className="muted">All applicable line items present.</p>
                    ) : (
                      <div className="missing-grid">
                        {missingOrder.map((stmt) => {
                          const items = currentMissing?.[stmt] ?? [];
                          if (!items.length) return null;
                          return (
                            <div key={stmt} className="missing-block">
                              <span className="missing-label">{humanLabel(stmt)}</span>
                              <div className="missing-items">
                                {items.map((item) => (
                                  <span key={item} className="missing-pill">
                                    {humanLabel(item)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </details>
                ) : (
                  <p className="muted">Missing item detail not available.</p>
                )}
              </div>
              <div className="quality-card">
                <div className="quality-header">
                  <h3 className="quality-title">Statement Ties</h3>
                  <span
                    className="pill"
                    data-tooltip="Accounting tie checks for the selected period."
                    aria-label="Accounting tie checks for the selected period."
                  >
                    Checks
                  </span>
                </div>
                {currentTies ? (
                  <div className="tie-metrics">
                    <div className="chip">
                      A − (L+E): {currentTies.bs_tie === null ? "n/a" : formatCurrency(currentTies.bs_tie)}
                    </div>
                    <div className="chip">
                      CF vs ΔCash: {currentTies.cf_tie === null ? "n/a" : formatCurrency(currentTies.cf_tie)}
                    </div>
                    <div
                      className={`chip pill ${currentTies.status === "fail" ? "danger" : currentTies.status === "warn" ? "warn" : "success"}`}
                      aria-label={
                        currentTies.status === "fail"
                          ? "Balance sheet does not tie; assets should equal liabilities plus equity."
                          : currentTies.status === "warn"
                          ? "Cash flow does not reconcile to the change in cash."
                          : "Statements tie within tolerance."
                      }
                      data-tooltip={
                        currentTies.status === "fail"
                          ? "Balance sheet off: Assets ≠ Liabilities + Equity. Check equity/liability mapping."
                          : currentTies.status === "warn"
                          ? "Cash flow off: CFO + CFI + CFF ≠ change in cash. Missing CF components or restricted cash?"
                          : "All statements tie within tolerance."
                      }
                    >
                      {currentTies.status || "ok"}
                    </div>
                  </div>
                ) : (
                  <p className="muted">Tie checks not available.</p>
                )}
              </div>
              <div className="quality-card">
                <div className="quality-header">
                  <h3 className="quality-title">Time-Travel Backtest</h3>
                  <span
                    className="pill"
                    data-tooltip="Forecast each period using only prior data, then score against actuals."
                    aria-label="Forecast each period using only prior data, then score against actuals."
                  >
                    Quality
                  </span>
                </div>
                {timeTravel ? (
                  <div className="metric-grid">
                    <div className="metric-item">
                      <div className="metric-label">MAE</div>
                      <div className="metric-value">{formatCurrency(timeTravel.mae)}</div>
                    </div>
                    <div className="metric-item">
                      <div className="metric-label">MAPE</div>
                      <div className="metric-value">{formatPercent(timeTravel.mape)}</div>
                    </div>
                    <div className="metric-item">
                      <div className="metric-label">Directional Acc.</div>
                      <div className={`metric-value${daToneClass}`}>
                        {Number.isNaN(timeTravel.directional_accuracy)
                          ? "N/A"
                          : formatPercent(timeTravel.directional_accuracy)}
                      </div>
                    </div>
                    <div className="metric-item">
                      <div className="metric-label">Interval Coverage</div>
                      <div className="metric-value">
                        {Number.isNaN(timeTravel.interval_coverage)
                          ? "N/A"
                          : formatPercent(timeTravel.interval_coverage)}
                      </div>
                    </div>
                    <div className="metric-item">
                      <div className="metric-label">Samples</div>
                      <div className="metric-value">{timeTravel.samples ?? "—"}</div>
                    </div>
                  </div>
                ) : (
                  <p className="muted">No time-travel backtest data.</p>
                )}
              </div>
            </div>
          )}
          {statements.length === 0 ? (
            <p className="muted">No statements for {ticker}. Ingest and parse first.</p>
          ) : (
            <div className="statement">
              {Object.entries(currentPeriodLines).map(([stmt, items]) => (
                <div key={stmt} className="statement-block">
                  <h3 style={{ marginBottom: "10px" }}>{humanLabel(stmt)}</h3>
                  <ul>
                    {items.map((item) => {
                      const driverSources = summary?.drivers?.[item.line_item ?? ""]?.sources;
                      const summarySource = currentSummarySources[item.line_item ?? ""];
                      const sourcePath = item.source_path || summarySource?.path;
                      const filingFallback = item.source_accession
                        ? summary?.filings?.find((f) => f.accession === item.source_accession)
                        : null;
                      const sourceForm = item.source_form || filingFallback?.form || null;
                      const sourceFiledAt = item.source_filed_at || filingFallback?.filed_at || null;
                      const sourceAccession = item.source_accession || null;
                      const sourceLink = sourcePath ? buildSourceUrl(sourcePath) : null;
                      const sourceLabel = `Source: ${buildSourceLabel(
                        ticker,
                        sourceForm,
                        currentPeriodKey || summarySource?.period_end || null
                      )}`;
                      const sourceUnit = item.unit || summarySource?.unit;
                      const showSource = Boolean(sourcePath || sourceAccession || summarySource);
                      const sourceTooltip = [
                        `Ticker: ${ticker}`,
                        `Form: ${sourceForm ? formatForm(sourceForm) : "n/a"}`,
                        `Filed: ${sourceFiledAt ? formatDate(sourceFiledAt) : "n/a"}`,
                        `Accession: ${sourceAccession || "n/a"}`,
                        `Statement: ${humanLabel(summarySource?.statement || stmt)}`,
                        `Line item: ${humanLabel(item.line_item)}`,
                        `Period end: ${currentPeriodKey || "n/a"}`,
                        `Unit: ${sourceUnit || "n/a"}`,
                        sourcePath ? `Path: ${sourcePath}` : null,
                      ]
                        .filter(Boolean)
                        .join(" • ");
                      const sourcePill = sourceLink ? (
                        <a
                          className="pill source-pill"
                          data-tooltip={sourceTooltip}
                          aria-label={sourceTooltip}
                          href={sourceLink}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {sourceLabel} {formatUnit(sourceUnit)}
                        </a>
                      ) : (
                        <span className="pill source-pill" data-tooltip={sourceTooltip} aria-label={sourceTooltip}>
                          {sourceLabel} {formatUnit(sourceUnit)}
                        </span>
                      );
                      return (
                        <li key={`${stmt}-${item.line_item}`}>
                          <div className="statement-meta">
                            <span>{humanLabel(item.line_item)}</span>
                            {showSource && sourcePill}
                            {driverSources && (
                              <span
                                className="muted"
                                data-tooltip="Historical periods used to compute forecast inputs (not predictions)."
                                aria-label="Historical periods used to compute forecast inputs (not predictions)."
                              >
                                Driver inputs (history): {driverSources.map((s) => s.period_end || "n/a").join(", ")}
                              </span>
                            )}
                          </div>
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
                      );
                    })}
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
