export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function pillClass(value: string | null | undefined): string {
  if (!value) return "pill";
  const v = value.toLowerCase();
  if (["bullish", "bull", "strong", "positive", "upgrade"].includes(v)) return "pill bull";
  if (["bearish", "bear", "weak", "negative", "downgrade"].includes(v)) return "pill bear";
  return "pill neutral";
}
