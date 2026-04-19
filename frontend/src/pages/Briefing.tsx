import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import type { BriefingView } from "../types";
import { todayISO } from "../util";
import { ErrorBox, Loader } from "../components/Loader";

export default function Briefing() {
  const { date: urlDate } = useParams();
  const navigate = useNavigate();
  const [date, setDate] = useState(urlDate ?? todayISO());
  const [data, setData] = useState<BriefingView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  async function load(d: string) {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await api.briefing(d));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(date);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  function onDateChange(next: string) {
    setDate(next);
    navigate(`/briefing/${next}`, { replace: true });
  }

  async function generate() {
    setRunning(true);
    setError(null);
    try {
      await api.runPipeline("meta", { date, wait: true });
      await load(date);
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>Briefing</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => onDateChange(e.target.value)}
        />
        <button onClick={() => load(date)} disabled={loading}>
          Refresh
        </button>
        <button onClick={generate} disabled={running}>
          {running ? "Generating…" : "Generate"}
        </button>
      </div>

      {error ? <ErrorBox error={error} /> : null}
      {loading ? <Loader /> : null}

      {data ? (
        <div className="card markdown">
          <p className="muted" style={{ fontSize: "0.8rem" }}>
            {data.model} · {data.tickers.length} tickers · generated{" "}
            {new Date(data.created_at).toLocaleString()}
          </p>
          <ReactMarkdown>{data.markdown}</ReactMarkdown>
        </div>
      ) : !loading && !error ? (
        <p className="muted">
          No briefing cached for {date}. Click Generate to produce one.
        </p>
      ) : null}
    </>
  );
}
