import Head from "next/head";

export default function Home() {
  return (
    <>
      <Head>
        <title>deltaisland research</title>
      </Head>
      <main className="page">
        <section className="hero">
          <h1>deltaisland research</h1>
          <p>Public-filings driven forecasts with audit-ready lineage.</p>
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
      </main>
    </>
  );
}
