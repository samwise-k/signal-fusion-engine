export function Loader({ label = "Loading…" }: { label?: string }) {
  return <p className="muted">{label}</p>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="error">Error: {msg}</div>;
}
