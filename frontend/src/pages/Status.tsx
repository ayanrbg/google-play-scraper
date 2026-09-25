import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useMe } from "../App";
import { Seg } from "../components/filters";
import { Loader, Stat } from "../components/ui";
import { fmtDate, fmtN } from "../format";

type Progress = { label: string; done: number; total: number; rate: number; eta_sec: number | null; at: string };
type Step = { step: string; status: "pending" | "running" | "ok" | "error"; started?: string; finished?: string; stats?: Record<string, any>; error?: string };
type Run = { id: number; job: string; status: string; started_at: string; finished_at: string | null; stats: Record<string, any>; error: string | null };
type StatusData = {
  apps: number; games_with_cards: number; tracked: number; prereg: number; radar: number; keywords: number; keywords_found: number;
  snapshot_days: number; last_snapshot: string | null; last_chart: string | null;
  runs: Record<string, Run>; history: Run[]; next_run: string; server_time: string; pending_run: boolean;
  current: { job: string; started_at: string; progress: Progress | null; remaining?: number } | null;
};
type LogLine = { id: number; ts: string; level: string; job: string | null; message: string };

const STEP_LABELS: Record<string, string> = {
  charts: "Чарты",
  expand: "Похожие игры, студии, предрегистрации",
  enrich: "Карточки новых игр",
  track: "Установки отслеживаемых игр",
  metrics: "Скоринг",
  keywords: "Ниши в поиске",
  cleanup: "Очистка старых данных",
  softlaunch: "Проверка софт-лончей (разово)",
};
// Second pass of a step within one run (enrich/metrics run again after keyword search)
const REPEAT_LABELS: Record<string, string> = {
  enrich: "Карточки игр, найденных в поиске",
  metrics: "Итоговый скоринг",
};
const PROGRESS_LABELS: Record<string, string> = {
  charts: "запросов чартов", enrich: "карточек", track: "игр", similar: "игр-образцов", developers: "страниц студий",
  suggest: "сидов", search: "запросов", "keyword-cards": "карточек из поиска", softlaunch: "игр проверено на софт-лонч",
};

// ---------- time helpers (server stores UTC without "Z") ----------
const utc = (v: string) => new Date(v.endsWith("Z") || v.includes("+") ? v : v + "Z");
const localTime = (v: string | null | undefined, withDate = true) =>
  v ? utc(v).toLocaleString("ru-RU", withDate ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
function dur(sec: number) {
  if (sec < 60) return `${Math.round(sec)} с`;
  if (sec < 3600) return `${Math.round(sec / 60)} мин`;
  const h = Math.floor(sec / 3600);
  return `${h} ч ${Math.round((sec - h * 3600) / 60)} мин`;
}
const span = (a?: string | null, b?: string | null) => (a ? dur(((b ? utc(b) : new Date()).getTime() - utc(a).getTime()) / 1000) : "—");

/** One human sentence per step from its raw stats. */
function summary(step: string, s: Record<string, any> | undefined): string {
  if (!s || !Object.keys(s).length) return "";
  const n = (v: any) => (typeof v === "number" ? v.toLocaleString("ru-RU") : "0");
  switch (step) {
    case "charts":
      return `${n(s.requests)} запросов, ошибок ${n(s.failed)} · игр в чартах ${n(s.charted_apps)} · новых ${n(s.new_apps)}`;
    case "expand":
      return `предрегистрации +${n(s.prereg?.new)} · похожие +${n(s.similar?.new)} · студий проверено ${n(s.developers?.developers)} (+${n(s.developers?.new)} игр)`;
    case "enrich":
      return `карточек ${n(s.ok)} из ${n(s.candidates)} · взято на отслеживание ${n(s.tracked)}` +
        (s.soft_launch ? ` · софт-лончей ${n(s.soft_launch)}` : "") +
        (s.revivals ? ` · возрождений ${n(s.revivals)}` : "") +
        ` · удалены из Google Play ${n(s.missing)} · ошибок ${n(s.failed)}`;
    case "track":
      return `обновлено ${n(s.ok)} из ${n(s.candidates)} · ошибок ${n(s.failed)} · снято с отслеживания ${n(s.untracked)}`;
    case "metrics":
      return `посчитано игр ${n(s.games)}`;
    case "keywords":
      return `сидов ${n(s.seeds)} · найдено запросов ${n(s.terms)} · разобрано ${n(s.analyzed)}` +
        (s.markets ? ` · языков ${Object.keys(s.markets).length}` : "");
    default:
      return "";
  }
}

function StepIcon({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    ok: ["✓", "var(--good)"], error: ["✕", "var(--bad)"], running: ["●", "var(--accent)"], pending: ["○", "var(--faint)"],
  };
  const [ch, color] = map[status] || map.pending;
  return (
    <span className={status === "running" ? "pulse" : ""} style={{ color, width: 18, display: "inline-block", textAlign: "center", fontWeight: 700 }}>
      {ch}
    </span>
  );
}

function ProgressBar({ p, remaining }: { p: Progress | null; remaining?: number }) {
  if (!p) {
    return remaining !== undefined ? <div className="muted" style={{ fontSize: 13 }}>осталось ≈ {fmtN(remaining)}</div> : null;
  }
  const pct = p.total ? (p.done / p.total) * 100 : 0;
  return (
    <div style={{ marginTop: 8 }}>
      <div className="meter" style={{ height: 8 }}>
        <i style={{ width: `${pct}%`, transition: "width .6s" }} />
      </div>
      <div className="row mono" style={{ justifyContent: "space-between", fontSize: 12, marginTop: 6, color: "var(--muted)" }}>
        <span>
          {p.done.toLocaleString("ru-RU")} / {p.total.toLocaleString("ru-RU")} {PROGRESS_LABELS[p.label] || p.label} · {pct.toFixed(0)}%
        </span>
        <span>
          {p.rate ? `${p.rate.toFixed(1)}/с` : ""}
          {p.eta_sec ? ` · осталось ~${dur(p.eta_sec)}` : ""}
        </span>
      </div>
    </div>
  );
}

function StepList({ steps, current }: { steps: Step[]; current: StatusData["current"] }) {
  const label = (i: number) => {
    const name = steps[i].step;
    const repeat = steps.slice(0, i).some((p) => p.step === name);
    return (repeat && REPEAT_LABELS[name]) || STEP_LABELS[name] || name;
  };
  return (
    <div className="stack" style={{ gap: 0 }}>
      {steps.map((s, i) => (
        <div key={i} style={{ padding: "10px 0", borderTop: i ? "1px solid var(--line)" : 0 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
            <span>
              <StepIcon status={s.status} /> <b>{label(i)}</b>
            </span>
            <span className="mono muted" style={{ fontSize: 12 }}>
              {s.status === "pending" ? "ждёт" : span(s.started, s.finished)}
            </span>
          </div>
          <div style={{ paddingLeft: 26 }}>
            {s.status === "running" && current && current.job === s.step && <ProgressBar p={current.progress} remaining={current.remaining} />}
            {s.status !== "running" && summary(s.step, s.stats) && <div className="muted" style={{ fontSize: 13 }}>{summary(s.step, s.stats)}</div>}
            {s.error && <div className="bad mono" style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{s.error}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Older runs (before step tracking) only have per-job rows; rebuild a step list from them. */
function stepsOf(run: Run, runs: Record<string, Run>, current: StatusData["current"]): Step[] {
  if (Array.isArray(run.stats?.steps)) return run.stats.steps;
  return ["charts", "expand", "enrich", "track", "metrics", "keywords"].map((job) => {
    const r = runs[job];
    const fresh = r && utc(r.started_at) >= utc(run.started_at);
    if (!fresh) return { step: job, status: run.status === "running" ? "pending" : "pending" } as Step;
    const status = current?.job === job ? "running" : (r.status as Step["status"]);
    return { step: job, status, started: r.started_at, finished: r.finished_at || undefined, stats: r.stats, error: r.error || undefined };
  });
}

export default function Status() {
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["status"], queryFn: () => api<StatusData>("/status"), refetchInterval: 10_000 });
  const [level, setLevel] = useState("info");
  const logs = useQuery({
    queryKey: ["logs", level],
    queryFn: () => api<LogLine[]>("/logs", { params: { level, limit: 300 } }),
    refetchInterval: 15_000,
    enabled: me.is_superadmin,
  });
  const [open, setOpen] = useState<number | null>(null);
  const run = useMutation({
    mutationFn: () => api("/admin/run", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
  if (q.isLoading || !q.data) return <Loader />;
  const d = q.data;
  const latest = d.history[0];
  const running = latest?.status === "running";

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Данные</h1>
          <p className="page-sub">
            Как идёт сбор. Страница обновляется сама. Время указано по вашему часовому поясу.
          </p>
        </div>
        {me.is_superadmin && (
          <div style={{ textAlign: "right" }}>
            <button className="btn primary" onClick={() => run.mutate()} disabled={running || d.pending_run || run.isPending}>
              {running ? "Сбор идёт…" : d.pending_run ? "Запуск в очереди…" : "Запустить сейчас"}
            </button>
            <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>следующий по расписанию: {localTime(d.next_run)}</div>
          </div>
        )}
      </div>

      <div className="grid-2" style={{ gridTemplateColumns: "1.2fr 1fr", marginBottom: 20, alignItems: "start" }}>
        <div className="panel panel-pad">
          <h3 className="panel-title">
            {running ? "Сейчас идёт сбор" : "Последний прогон"}
            {latest && (
              <span className="faint" style={{ fontWeight: 400 }}>
                {" "}· начат {localTime(latest.started_at)} · {running ? `идёт ${span(latest.started_at)}` : `занял ${span(latest.started_at, latest.finished_at)}`}
              </span>
            )}
          </h3>
          {latest ? (
            <StepList steps={stepsOf(latest, d.runs, d.current)} current={d.current} />
          ) : (
            <p className="muted">Прогонов ещё не было. Нажмите «Запустить сейчас» или дождитесь расписания.</p>
          )}
          {latest?.error && <div className="bad" style={{ fontSize: 12, marginTop: 8 }}>{latest.error}</div>}
        </div>

        <div className="stack">
          <div className="stats" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Stat label="Игр найдено" value={fmtN(d.apps)} note={`с карточками ${fmtN(d.games_with_cards)}`} />
            <Stat label="Отслеживаем" value={fmtN(d.tracked)} note={`моложе года · пре-рег ${fmtN(d.prereg)}`} />
            <Stat label="На радаре" value={fmtN(d.radar)} />
            <Stat label="Ниши" value={fmtN(d.keywords)} note={`найдено запросов ${fmtN(d.keywords_found)}`} />
            <Stat label="Дней истории" value={d.snapshot_days} note={`последний срез ${fmtDate(d.last_snapshot)}`} />
            <Stat label="Чарты" value={fmtDate(d.last_chart)} />
          </div>
          <div className="banner info" style={{ margin: 0 }}>
            <b>Зрелость данных: {d.snapshot_days} из 15 дней.</b> Скорость за неделю надёжна с ~8-го дня, ускорение
            «неделя к неделе» — с ~15-го. До этого скорость на радаре оценочная (помечена «~»).
          </div>
        </div>
      </div>

      <h3 className="panel-title">История прогонов</h3>
      <div className="table-wrap" style={{ marginBottom: 24 }}>
        <table className="data">
          <thead>
            <tr>
              <th>Начало</th>
              <th>Статус</th>
              <th className="r">Длительность</th>
              <th>Итог</th>
            </tr>
          </thead>
          <tbody>
            {d.history.map((h) => {
              const steps = Array.isArray(h.stats?.steps) ? (h.stats.steps as Step[]) : [];
              const failed = steps.filter((s) => s.status === "error").map((s) => STEP_LABELS[s.step] || s.step);
              const charts = steps.find((s) => s.step === "charts")?.stats;
              const enrich = steps.find((s) => s.step === "enrich")?.stats;
              return (
                <Fragment key={h.id}>
                  <tr className="clickable" onClick={() => setOpen(open === h.id ? null : h.id)}>
                    <td className="num">{localTime(h.started_at)}</td>
                    <td className={h.status === "ok" ? "good" : h.status === "error" ? "bad" : "accent"}>
                      {h.status === "ok" ? "✓ успешно" : h.status === "running" ? "● идёт" : failed.length ? `✕ ошибки: ${failed.join(", ")}` : `✕ ${h.error || "ошибка"}`}
                    </td>
                    <td className="r num">{span(h.started_at, h.finished_at)}</td>
                    <td className="muted" style={{ fontSize: 12.5 }}>
                      {charts ? `в чартах ${fmtN(charts.charted_apps)} игр` : ""}
                      {enrich ? ` · новых карточек ${fmtN(enrich.ok)}` : ""}
                      {steps.length ? "" : "подробности до обновления системы не сохранялись"}
                      <span className="faint"> {open === h.id ? "▲" : "▼"}</span>
                    </td>
                  </tr>
                  {open === h.id && (
                    <tr>
                      <td colSpan={4} style={{ whiteSpace: "normal", background: "var(--bg)" }}>
                        <StepList steps={stepsOf(h, d.runs, h.status === "running" ? d.current : null)} current={h.status === "running" ? d.current : null} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {!d.history.length && (
              <tr>
                <td colSpan={4} className="muted">Пока пусто</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {me.is_superadmin && (
        <>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
            <h3 className="panel-title" style={{ margin: 0 }}>Журнал</h3>
            <div style={{ width: 320 }}>
              <Seg options={[["info", "Все события"], ["warning", "Предупреждения"], ["error", "Ошибки"]]} value={level} onChange={setLevel} />
            </div>
          </div>
          <div className="panel log">
            {logs.data?.length ? (
              logs.data.map((l) => (
                <div key={l.id} className={`log-line ${l.level.toLowerCase()}`}>
                  <span className="log-ts">{localTime(l.ts, false)}</span>
                  <span className="log-lvl">{l.level === "INFO" ? "·" : l.level === "WARNING" ? "!" : "✕"}</span>
                  {l.job && <span className="log-job">{l.job}</span>}
                  <span className="log-msg">{l.message}</span>
                </div>
              ))
            ) : (
              <div className="muted" style={{ padding: 16 }}>
                {logs.isLoading ? "Загрузка…" : "Событий нет. Журнал ведётся с момента обновления системы."}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
