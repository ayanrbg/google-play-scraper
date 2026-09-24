import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Chips } from "../components/filters";
import { Empty, Loader, Score } from "../components/ui";
import { fmtN } from "../format";

type Studio = {
  developer_id: string; developer: string; hot_games: number; v7_sum: number; best_trend: number;
  games: { app_id: string; title: string; icon_url: string; trend_score: number; v7: number | null; installs: number | null }[];
};

export default function Studios() {
  const [minTrend, setMinTrend] = useState("40");
  const q = useQuery({ queryKey: ["studios", minTrend], queryFn: () => api<Studio[]>("/studios", { params: { min_trend: minTrend || 0 } }) });
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Студии</h1>
          <p className="page-sub">
            Небольшие студии без брендов, у которых сразу несколько свежих игр набирают ход. Смотрите, что они выпускают: часто это
            быстрые тесты механик, и удачные потом масштабируют.
          </p>
        </div>
        <Chips options={[["30", "Score 30+"], ["40", "40+"], ["55", "55+"], ["70", "70+"]]} value={minTrend} onChange={setMinTrend} />
      </div>
      {q.isLoading ? (
        <Loader />
      ) : !q.data?.length ? (
        <div className="panel"><Empty title="Пока пусто">Нужно несколько дней данных.</Empty></div>
      ) : (
        <div className="stack">
          {q.data.map((s, i) => (
            <div key={s.developer_id} className="panel panel-pad" style={{ animation: "rowIn .35s both", animationDelay: `${Math.min(i, 12) * 30}ms` }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <h3 className="panel-title" style={{ margin: 0 }}>{s.developer}</h3>
                <span className="mono muted" style={{ fontSize: 12 }}>
                  {s.hot_games} горячих · {fmtN(s.v7_sum)}/день
                </span>
              </div>
              <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
                {s.games.slice(0, 8).map((g) => (
                  <Link key={g.app_id} to={`/game/${encodeURIComponent(g.app_id)}`} className="panel" style={{ padding: 10, width: 230, display: "flex", gap: 10, alignItems: "center", background: "var(--bg)" }}>
                    {g.icon_url ? <img className="app-icon" src={g.icon_url} alt="" loading="lazy" /> : <div className="app-icon" />}
                    <div className="app-meta">
                      <div className="app-title" style={{ fontSize: 13 }}>{g.title}</div>
                      <div className="row" style={{ gap: 6, fontSize: 12 }}>
                        <Score value={g.trend_score} />
                        <span className="num muted">{fmtN(g.v7)}/д</span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
