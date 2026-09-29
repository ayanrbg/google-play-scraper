import { ReactNode } from "react";
import { FLAG_SHORT } from "../format";

export function BrandMark({ size = 30, animate = false }: { size?: number; animate?: boolean }) {
  return (
    <svg className={`brand-mark${animate ? " drawing" : ""}`} width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M4 26.5H28M4 18.5H28M4 10.5H28" stroke="var(--accent)" strokeOpacity=".2" strokeWidth="1.2" />
      <path className="mark-line" pathLength={1} d="M4.5 23.5L11 16.5L16.5 20L26 9" fill="none" stroke="var(--accent)"
        strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle className="mark-dot" cx="26" cy="9" r="2.6" fill="var(--accent)" />
    </svg>
  );
}

export function Loader() {
  return (
    <div className="loader">
      <BrandMark size={40} animate />
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <BrandMark size={40} />
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

export function Flags({ flags, prereg, age, softLaunch, revival, hidden }: {
  flags: string[]; prereg?: boolean; age?: number | null; softLaunch?: string[] | null; revival?: boolean; hidden?: boolean;
}) {
  return (
    <>
      {hidden && (
        <span className="flag gem" title="Скрытая находка: молодая, растёт, не бренд — и почти не видна в чартах. Такую руками не найти.">
          ◆ находка
        </span>
      )}
      {revival && (
        <span className="flag revival" title="Старая игра (больше года), которая снова пошла вверх в Movers & Shakers: волна тренда">
          ↻ возрождение
        </span>
      )}
      {prereg && <span className="flag prereg">пре-рег</span>}
      {softLaunch && softLaunch.length > 0 && (
        <span className="flag soft" title={`До глобального запуска тестировалась в: ${softLaunch.map((c) => c.toUpperCase()).join(", ")}. Возраст считается с глобального запуска.`}>
          софт-лонч
        </span>
      )}
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

