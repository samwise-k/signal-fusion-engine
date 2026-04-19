import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { TickerHistory, TickerSnapshot } from "../types";
import { fmtNum, fmtPct, pillClass } from "../util";
import { ErrorBox, Loader } from "../components/Loader";

export default function TickerDetail() {
  const { symbol = "" } = useParams();
  const [snap, setSnap] = useState<TickerSnapshot | null>(null);
  const [history, setHistory] = useState<TickerHistory | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.tickerDetail(symbol), api.tickerHistory(symbol, 30)])
      .then(([s, h]) => {
        if (cancelled) return;
        setSnap(s);
        setHistory(h);
      })
      .catch((e) => !cancelled && setError(e))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (loading) return <Loader />;
  if (error) return <ErrorBox error={error} />;
  if (!snap) return <p className="muted">No data.</p>;

  return (
    <>
      <p className="muted">
        <Link to="/">← Watchlist</Link>
      </p>
      <h1>
        {snap.ticker}{" "}
        <span className="muted" style={{ fontSize: "1rem", fontWeight: 400 }}>
          {snap.sector ?? ""}
        </span>
      </h1>

      <div className="grid-3">
        <SentimentCard snap={snap} />
        <QuantCard snap={snap} />
        <EnrichmentCard snap={snap} />
      </div>

      <HistoryCard history={history} />
    </>
  );
}

function SentimentCard({ snap }: { snap: TickerSnapshot }) {
  const s = snap.sentiment;
  return (
    <div className="card">
      <h3>Sentiment</h3>
      {s ? (
        <>
          <p>
            <span className={pillClass(s.sentiment_direction)}>
              {s.sentiment_direction}
            </span>{" "}
            <span className="muted">score {fmtNum(s.sentiment_score)}</span>
          </p>
          <p className="muted">
            As of {s.as_of} · Δ7d {fmtNum(s.sentiment_delta_7d)}
          </p>
          {s.key_topics?.length ? (
            <p className="muted">Topics: {s.key_topics.join(", ")}</p>
          ) : null}
          {s.notable_headlines?.length ? (
            <>
              <h4 style={{ marginBottom: "0.25rem" }}>Headlines</h4>
              <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
                {s.notable_headlines.slice(0, 5).map((h, i) => (
                  <li key={i} style={{ fontSize: "0.85rem" }}>
                    {String(h.title ?? h.headline ?? JSON.stringify(h))}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      ) : (
        <p className="muted">No sentiment data.</p>
      )}
    </div>
  );
}

function QuantCard({ snap }: { snap: TickerSnapshot }) {
  const q = snap.quantitative;
  return (
    <div className="card">
      <h3>Quant</h3>
      {q ? (
        <>
          <p>
            <span className={pillClass(q.health_score)}>{q.health_score}</span>{" "}
            <span className="muted">as of {q.as_of}</span>
          </p>
          <table>
            <tbody>
              <tr><td>Close</td><td>{fmtNum(q.close)}</td></tr>
              <tr><td>1d</td><td>{fmtPct(q.change_1d)}</td></tr>
              <tr><td>5d</td><td>{fmtPct(q.change_5d)}</td></tr>
              <tr><td>20d</td><td>{fmtPct(q.change_20d)}</td></tr>
              <tr><td>RSI-14</td><td>{fmtNum(q.rsi_14, 1)}</td></tr>
              <tr><td>MACD</td><td>{q.macd_signal ?? "—"}</td></tr>
              <tr><td>&gt; 50SMA</td><td>{boolStr(q.above_50sma)}</td></tr>
              <tr><td>&gt; 200SMA</td><td>{boolStr(q.above_200sma)}</td></tr>
              <tr><td>Vol vs 20d</td><td>{fmtNum(q.volume_vs_20d_avg)}</td></tr>
              <tr>
                <td>Rel 5d ({q.sector_etf ?? "—"})</td>
                <td>{fmtPct(q.relative_return_5d)}</td>
              </tr>
            </tbody>
          </table>
        </>
      ) : (
        <p className="muted">No quant data.</p>
      )}
    </div>
  );
}

function EnrichmentCard({ snap }: { snap: TickerSnapshot }) {
  const e = snap.enrichment;
  return (
    <div className="card">
      <h3>Enrichment</h3>
      {e ? (
        <>
          <p className="muted">As of {e.as_of}</p>
          <h4 style={{ marginBottom: "0.25rem" }}>Insider</h4>
          <pre style={{ fontSize: "0.8rem", margin: 0 }}>
            {JSON.stringify(e.insider_trades, null, 2)}
          </pre>
          <h4 style={{ marginBottom: "0.25rem", marginTop: "0.75rem" }}>
            Analyst
          </h4>
          <pre style={{ fontSize: "0.8rem", margin: 0 }}>
            {JSON.stringify(e.analyst_activity, null, 2)}
          </pre>
          {e.next_earnings ? (
            <>
              <h4 style={{ marginBottom: "0.25rem", marginTop: "0.75rem" }}>
                Next earnings
              </h4>
              <pre style={{ fontSize: "0.8rem", margin: 0 }}>
                {JSON.stringify(e.next_earnings, null, 2)}
              </pre>
            </>
          ) : null}
        </>
      ) : (
        <p className="muted">No enrichment data.</p>
      )}
    </div>
  );
}

function HistoryCard({ history }: { history: TickerHistory | null }) {
  if (!history) return null;
  return (
    <div className="grid-2">
      <div className="card">
        <h3>Sentiment history</h3>
        {history.sentiment.length === 0 ? (
          <p className="muted">No history yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Direction</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {history.sentiment.map((r) => (
                <tr key={r.as_of}>
                  <td>{r.as_of}</td>
                  <td>
                    <span className={pillClass(r.direction)}>
                      {r.direction}
                    </span>
                  </td>
                  <td>{fmtNum(r.score ?? null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h3>Quant history</h3>
        {history.quant.length === 0 ? (
          <p className="muted">No history yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Close</th>
                <th>1d</th>
                <th>RSI</th>
                <th>Health</th>
              </tr>
            </thead>
            <tbody>
              {history.quant.map((r) => (
                <tr key={r.as_of}>
                  <td>{r.as_of}</td>
                  <td>{fmtNum(r.close ?? null)}</td>
                  <td>{fmtPct(r.change_1d ?? null)}</td>
                  <td>{fmtNum(r.rsi_14 ?? null, 1)}</td>
                  <td>
                    <span className={pillClass(r.health_score)}>
                      {r.health_score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function boolStr(v: boolean | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v ? "yes" : "no";
}
