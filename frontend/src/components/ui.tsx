import { ReactNode } from "react";
import { FLAG_SHORT } from "../format";

export function RadarMark({ size = 30, spin = false }: { size?: number; spin?: boolean }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="16" r="14" fill="none" stroke="var(--accent)" strokeOpacity=".25" strokeWidth="1.2" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="var(--accent)" strokeOpacity=".4" strokeWidth="1.2" />
      <circle cx="16" cy="16" r="4" fill="none" stroke="var(--accent)" strokeOpacity=".55" strokeWidth="1.2" />
      <g style={spin ? { transformOrigin: "16px 16px", animation: "spin 1.6s linear infinite" } : undefined}>
        <path d="M16 16 L27 8" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      </g>
      <circle cx="23" cy="11" r="2" fill="var(--accent)" />
    </svg>
  );
}

export function Loader() {
  return (
    <div className="loader">
      <RadarMark size={40} spin />
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <RadarMark size={40} />
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}

/** Trend Score as a signal-strength meter: 10 bars. */
export function Score({ value }: { value: number }) {
  const on = Math.round(value / 10);
  return (
    <span className="score" title={`Trend Score ${value}/100`}>
      <span className="score-num">{Math.round(value)}</span>
      <span className="score-bars">
        {Array.from({ length: 10 }, (_, i) => (
          <i key={i} className={i < on ? "on" : ""} style={{ height: 4 + i * 1.2 }} />
        ))}
      </span>
    </span>
  );
}

/** Daily installs sparkline. Unknown days (Google counter not refreshed yet) draw as a dashed tail. */
export function Sparkline({ data, width = 110, height = 28 }: { data: (number | null)[]; width?: number; height?: number }) {
  const known = data.map((v, i) => [i, v] as const).filter(([, v]) => v !== null) as [number, number][];
  if (known.length < 2) return <span className="faint mono" style={{ fontSize: 11 }}>мало данных</span>;
  const max = Math.max(...known.map(([, v]) => v), 1);
  const step = width / Math.max(data.length - 1, 1);
  const y = (v: number) => height - 2 - (v / max) * (height - 4);
  const pts = known.map(([i, v]) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`);
  const last = known[known.length - 1];
  const lastX = last[0] * step;
  const area = `M0,${height} L${pts.join(" L")} L${lastX.toFixed(1)},${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <path d={area} fill="var(--accent-soft)" />
      <polyline points={pts.join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" />
      {last[0] < data.length - 1 && (
        <line x1={lastX} y1={y(last[1])} x2={width} y2={y(last[1])} stroke="var(--faint)" strokeDasharray="2 3" strokeWidth="1">
          <title>Google ещё не обновил счётчик установок</title>
        </line>
      )}
      <circle cx={lastX} cy={y(last[1])} r="2" fill="var(--accent)" />
    </svg>
  );
}

export function Flags({ flags, prereg, age }: { flags: string[]; prereg?: boolean; age?: number | null }) {
  return (
    <>
      {prereg && <span className="flag prereg">пре-рег</span>}
      {age !== null && age !== undefined && age <= 14 && !prereg && <span className="flag new">новинка</span>}
      {flags.map((f) => (
        <span key={f} className={`flag ${f}`}>
          {FLAG_SHORT[f] || f}
        </span>
      ))}
    </>
  );
}

export function Meter({ value, max = 100, tone }: { value: number | null; max?: number; tone?: "warn" | "bad" }) {
  const pct = Math.max(0, Math.min(100, ((value || 0) / max) * 100));
  return (
    <div className={`meter ${tone || ""}`}>
      <i style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ←
      </button>
      <span>
        {page} / {pages}
      </span>
      <button className="btn sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        →
      </button>
    </div>
  );
}

export function SortTh({ label, field, sort, dir, onSort, right, title }: {
  label: string; field: string; sort: string; dir: string; onSort: (f: string) => void; right?: boolean; title?: string;
}) {
  const on = sort === field;
  return (
    <th className={`sortable ${on ? "sorted" : ""} ${right ? "r" : ""}`} onClick={() => onSort(field)} title={title}>
      {label}
      {on ? (dir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
}

