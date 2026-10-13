import { Info } from "lucide-react";

/** One transparent indicator: value, numerator/denominator and formula on demand. Never shows 0 % when there is no valid data. */
export function Metric({ label, m, testid }) {
  if (!m) return null;
  const unavailable = m.value == null;
  return <div className="surface p-3 min-w-[170px]" data-testid={testid}>
    <p className="overline flex items-center gap-1">{label}<span title={m.formula || ""} aria-label="définition"><Info className="h-3 w-3 opacity-60" /></span></p>
    <p className={`num text-xl font-bold mt-1 ${unavailable ? "text-muted-foreground text-sm" : ""}`}>{m.display}</p>
    {!unavailable && <p className="num text-[11px] text-muted-foreground">{m.numerator} / {m.denominator}</p>}
    {m.formula && <p className="text-[10px] text-muted-foreground mt-1 leading-tight">{m.formula}</p>}
    {m.note && <p className="text-[10px] text-amber-700 mt-1">{m.note}</p>}
  </div>;
}

export function Empty({ children, testid }) {
  return <p className="text-sm text-muted-foreground border border-dashed rounded-md p-4" data-testid={testid}>{children}</p>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return <div role="alert" className="text-sm text-red-700 bg-red-500/10 rounded-md p-3 flex items-center justify-between gap-2" data-testid="growth-error">
    <span>{error}</span>{onRetry && <button className="underline" onClick={onRetry}>Réessayer</button>}
  </div>;
}

export function Stale({ at }) {
  if (!at) return null;
  const days = (Date.now() - new Date(at)) / 86400000;
  if (days < 7) return null;
  return <span className="ml-2 text-[10px] rounded-sm px-1 bg-amber-500/15 text-amber-700" data-testid="growth-stale">données de {Math.floor(days)} j</span>;
}
