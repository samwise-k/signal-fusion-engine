import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { WatchlistSnapshot } from "../types";
import { fmtNum, fmtPct, pillClass, todayISO } from "../util";
import { ErrorBox, Loader } from "../components/Loader";

export default function Watchlist() {
  const [date, setDate] = useState(todayISO());
  const [data, setData] = useState<WatchlistSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.watchlistSnapshot(date));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  async function trigger(engine: "sentiment" | "quant" | "enrichment" | "meta") {
    setRunning(engine);
    try {
      await api.runPipeline(engine, { date });
    } catch (e) {
      setError(e);
    } finally {
      setRunning(null);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>Watchlist</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <button onClick={load} disabled={loading}>
          Refresh
        </button>
        <span className="muted" style={{ marginLeft: "auto" }}>Run pipeline:</span>
        {(["sentiment", "quant", "enrichment", "meta"] as const).map((eng) => (
          <button
            key={eng}
            onClick={() => trigger(eng)}
            disabled={running !== null}
          >
            {running === eng ? `${eng}…` : eng}
          </button>
        ))}
      </div>

      {error ? <ErrorBox error={error} /> : null}
      {loading && !data ? <Loader /> : null}

      {data ? (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Sector</th>
                <th>Sentiment</th>
                <th>Δ7d</th>
                <th>Close</th>
                <th>1d</th>
                <th>5d</th>
                <th>RSI</th>
                <th>Health</th>
                <th>Earnings</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.ticker}>
                  <td>
                    <Link to={`/tickers/${e.ticker}`}>{e.ticker}</Link>
                  </td>
                  <td className="muted">{e.sector ?? "—"}</td>
                  <td>
                    {e.sentiment ? (
                      <>
                        <span className={pillClass(e.sentiment.sentiment_direction)}>
                          {e.sentiment.sentiment_direction}
                        </span>{" "}
                        <span className="muted">
                          {fmtNum(e.sentiment.sentiment_score)}
                        </span>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>{fmtNum(e.sentiment?.sentiment_delta_7d ?? null)}</td>
                  <td>{fmtNum(e.quantitative?.close ?? null)}</td>
                  <td>{fmtPct(e.quantitative?.change_1d ?? null)}</td>
                  <td>{fmtPct(e.quantitative?.change_5d ?? null)}</td>
                  <td>{fmtNum(e.quantitative?.rsi_14 ?? null, 1)}</td>
                  <td>
                    {e.quantitative ? (
                      <span className={pillClass(e.quantitative.health_score)}>
                        {e.quantitative.health_score}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="muted">
                    {earningsCell(e.enrichment?.next_earnings)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}>
            Snapshot as of {data.as_of}. Sentiment/quant/enrichment values show
            the most recent row on or before that date.
          </p>
        </div>
      ) : null}
    </>
  );
}

function earningsCell(next: Record<string, unknown> | null | undefined) {
  if (!next) return "—";
  const date = next.date ?? next.earnings_date;
  const days = next.days_until;
  if (date && typeof days === "number") return `${date} (${days}d)`;
  if (date) return String(date);
  return "—";
}
