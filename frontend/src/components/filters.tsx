import { ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useIsMobile } from "./ui";

/** URL-backed filter state: shareable links and saved views for free. */
export function useUrlFilters(defaults: Record<string, string>) {
  const [params, setParams] = useSearchParams();
  const get = (k: string) => (params.has(k) ? params.get(k)! : defaults[k] ?? "");
  const set = (patch: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === (defaults[k] ?? "")) next.delete(k);
      else next.set(k, v);
    }
    if (resetPage && !("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  };
  const all = () => {
    const out: Record<string, string> = { ...defaults };
    params.forEach((v, k) => (out[k] = v));
    return out;
  };
  const reset = () => setParams(new URLSearchParams(), { replace: true });
  const replaceAll = (values: Record<string, string>) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(values)) if (v !== (defaults[k] ?? "")) next.set(k, v);
    setParams(next, { replace: true });
  };
  return { get, set, all, reset, replaceAll, params };
}

export function Chips({ options, value, onChange, multi }: {
  options: [string, string][]; value: string; onChange: (v: string) => void; multi?: boolean;
}) {
  const selected = multi ? value.split(",").filter(Boolean) : [value];
  const toggle = (v: string) => {
    if (!multi) return onChange(v === value ? "" : v);
    const s = new Set(selected);
    s.has(v) ? s.delete(v) : s.add(v);
    onChange([...s].join(","));
  };
  return (
    <div className="chips">
      {options.map(([v, label]) => (
        <button key={v} type="button" className={`chip ${selected.includes(v) ? "on" : ""}`} onClick={() => toggle(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Seg({ options, value, onChange }: { options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="seg">
      {options.map(([v, label]) => (
        <button key={v} type="button" className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** Text/number input that commits after the user stops typing. */
export function LazyInput({ value, onCommit, placeholder, type = "text" }: {
  value: string; onCommit: (v: string) => void; placeholder?: string; type?: string;
}) {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => onCommit(local), 450);
    return () => clearTimeout(t);
  }, [local]);
  return <input className="input" type={type} value={local} placeholder={placeholder} onChange={(e) => setLocal(e.target.value)} />;
}

export function FGroup({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="fgroup">
      <div className="fgroup-title">
        <span>{title}</span>
        {hint && <span className="hint">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

/** Collapsible filter column; remembered per browser. On phones it is a full-screen sheet that always starts closed. */
export function useFiltersOpen() {
  const mobile = useIsMobile();
  const [column, setColumn] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem("filters_open");
      if (v !== null) return v === "1";
    } catch {}
    return window.innerWidth > 1100;
  });
  const [sheet, setSheet] = useState(false);
  useEffect(() => setSheet(false), [mobile]);
  const toggle = () => {
    if (mobile) return setSheet(!sheet);
    setColumn(!column);
    try {
      localStorage.setItem("filters_open", column ? "0" : "1");
    } catch {}
  };
  return { open: mobile ? sheet : column, toggle, mobile };
}

/** The filter column, or on phones a sheet over the page with a sticky "show results" bar. */
export function FilterPanel({ panel, onReset, result, children }: {
  panel: ReturnType<typeof useFiltersOpen>; onReset: () => void; result: string; children: ReactNode;
}) {
  const sheet = panel.mobile && panel.open;
  useEffect(() => {
    if (!sheet) return;
    document.body.classList.add("locked");
    return () => document.body.classList.remove("locked");
  }, [sheet]);
  if (!panel.open) return null;
  return (
    <aside className="panel filters">
      {sheet && (
        <div className="sheet-head">
          <b>Фильтры</b>
          <button className="btn sm ghost" onClick={panel.toggle} aria-label="Закрыть">
            ✕
          </button>
        </div>
      )}
      {children}
      {sheet ? (
        <div className="sheet-foot">
          <button className="btn ghost" onClick={onReset}>
            Сбросить
          </button>
          <button className="btn primary grow" onClick={panel.toggle}>
            Показать {result}
          </button>
        </div>
      ) : (
        <div className="fgroup">
          <button className="btn sm ghost" onClick={onReset}>
            Сбросить всё
          </button>
        </div>
      )}
    </aside>
  );
}

/** Sorting for card lists, where there are no column headers to click. */
export function SortSelect({ options, sort, dir, onChange }: {
  options: [field: string, label: string, dir: string][]; sort: string; dir: string; onChange: (sort: string, dir: string) => void;
}) {
  return (
    <div className="sort-select">
      <select className="select" value={sort} onChange={(e) => onChange(e.target.value, options.find(([f]) => f === e.target.value)?.[2] || "desc")}>
        {options.map(([f, label]) => (
          <option key={f} value={f}>
            {label}
          </option>
        ))}
      </select>
      <button className="btn sm" onClick={() => onChange(sort, dir === "desc" ? "asc" : "desc")} title="Направление сортировки">
        {dir === "desc" ? "↓" : "↑"}
      </button>
    </div>
  );
}

export function activeCount(values: Record<string, string>, defaults: Record<string, string>) {
  return Object.keys(defaults).filter((k) => !["sort", "dir", "page"].includes(k) && (values[k] ?? "") !== defaults[k]).length;
}
