import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useMe } from "../App";
import { Loader, Stat } from "../components/ui";
import { fmtDate, fmtDateTime, fmtN } from "../format";

type Run = { status: string; started_at: string; finished_at: string | null; stats: Record<string, any>; error: string | null };
type StatusData = {
  apps: number; tracked: number; radar: number; keywords: number; last_snapshot: string | null; last_chart: string | null;
  runs: Record<string, Run>; pending_run: boolean;
};

const JOB_LABELS: Record<string, string> = {
  daily: "Весь конвейер",
  charts: "Чарты 37 стран × 18 жанров × 4 чарта",
  expand: "Похожие, студии, предрегистрации",
  enrich: "Карточки новых игр",
  track: "Ежедневные установки",
  metrics: "Скоринг",
  keywords: "Ниши в поиске",
};

function duration(r: Run) {
  if (!r.finished_at) return "идёт…";
  const s = (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000;
  return s > 3600 ? `${(s / 3600).toFixed(1)} ч` : s > 60 ? `${Math.round(s / 60)} мин` : `${Math.round(s)} с`;
}

export default function Status() {
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["status"], queryFn: () => api<StatusData>("/status"), refetchInterval: 30_000 });
  const run = useMutation({
    mutationFn: () => api("/admin/run", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
  if (q.isLoading || !q.data) return <Loader />;
  const d = q.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Данные</h1>
          <p className="page-sub">
            Конвейер запускается раз в сутки. Установки в Google Play общие для всего мира, поэтому снимаются один раз в день
            по каждой игре. Чарты снимаются по каждой стране.
          </p>
        </div>
        {me.is_superadmin && (
          <button className="btn primary" onClick={() => run.mutate()} disabled={d.pending_run || run.isPending}>
            {d.pending_run ? "Запуск в очереди…" : "Запустить сейчас"}
          </button>
        )}
      </div>

      <div className="banner info">
        <b>Зрелость данных.</b> Скорость за 7 дней надёжна после ~8 дней наблюдений за игрой, ускорение (неделя к неделе) — после
        ~15. Google обновляет счётчик установок с задержкой 1–3 дня: это уже учтено в расчётах.
      </div>

      <div className="stats" style={{ marginBottom: 20 }}>
        <Stat label="Игр в базе" value={fmtN(d.apps)} />
        <Stat label="Отслеживаем ежедневно" value={fmtN(d.tracked)} note="моложе года + предрегистрации" />
        <Stat label="На радаре" value={fmtN(d.radar)} />
        <Stat label="Ниш разобрано" value={fmtN(d.keywords)} />
        <Stat label="Последние установки" value={fmtDate(d.last_snapshot)} />
        <Stat label="Последние чарты" value={fmtDate(d.last_chart)} />
      </div>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Этап</th>
              <th>Статус</th>
              <th>Запуск</th>
              <th className="r">Длительность</th>
              <th>Итог</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(JOB_LABELS).map(([job, label]) => {
              const r = d.runs[job];
              return (
                <tr key={job}>
                  <td>
                    <b>{job}</b> <span className="muted">— {label}</span>
                  </td>
                  <td className={r?.status === "ok" ? "good" : r?.status === "error" ? "bad" : "warn"}>{r ? r.status : "не запускался"}</td>
                  <td className="num muted">{r ? fmtDateTime(r.started_at) : "—"}</td>
                  <td className="r num">{r ? duration(r) : "—"}</td>
                  <td style={{ whiteSpace: "normal", maxWidth: 520, fontSize: 12 }} className="mono muted">
                    {r && Object.entries(r.stats || {}).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}
                    {r?.error && <div className="bad" style={{ whiteSpace: "pre-wrap" }}>{r.error}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
