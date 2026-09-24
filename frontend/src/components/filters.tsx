import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

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

/** Collapsible filter column; remembered per browser, collapsed by default on narrow screens. */
export function useFiltersOpen() {
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem("filters_open");
      if (v !== null) return v === "1";
    } catch {}
    return window.innerWidth > 1100;
  });
  const toggle = () => {
    setOpen(!open);
    try {
      localStorage.setItem("filters_open", open ? "0" : "1");
    } catch {}
  };
  return { open, toggle };
}

export function activeCount(values: Record<string, string>, defaults: Record<string, string>) {
  return Object.keys(defaults).filter((k) => !["sort", "dir", "page"].includes(k) && (values[k] ?? "") !== defaults[k]).length;
}
