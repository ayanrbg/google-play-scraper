import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Seg } from "../components/filters";
import { Empty, Loader } from "../components/ui";
import { fmtFull, fmtN, fmtPct } from "../format";

type G = { genre_id: string; genre: string; games: number; indie: number; hot: number; indie_v7_sum: number; indie_v7_median: number; indie_share: number };

export default function Genres() {
  const [age, setAge] = useState("180");
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["genres", age], queryFn: () => api<G[]>("/genres", { params: { max_age: age } }) });
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Жанры</h1>
          <p className="page-sub">
            Куда сейчас идут установки молодых игр без брендов. Сумма скоростей показывает объём спроса, медиана — насколько
            типичная инди-игра в жанре получает трафик, «горячие» — игры со Score 50+.
          </p>
        </div>
        <div style={{ width: 280 }}>
          <Seg options={[["30", "≤ 30 дн"], ["90", "≤ 90"], ["180", "≤ 180"], ["365", "≤ года"]]} value={age} onChange={setAge} />
        </div>
      </div>
      {q.isLoading ? (
        <Loader />
      ) : !q.data?.length ? (
        <div className="panel"><Empty title="Данных пока нет" /></div>
      ) : (
        <div className="stack">
          <div className="panel panel-pad">
            <h3 className="panel-title">Установок в день у молодых инди-игр, сумма</h3>
            <div style={{ height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={q.data} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid stroke="var(--line)" horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => fmtN(v)} stroke="var(--faint)" fontSize={11} />
                  <YAxis type="category" dataKey="genre" width={110} stroke="var(--faint)" fontSize={11} />
                  <Tooltip
                    contentStyle={{ background: "var(--bg-2)", border: "1px solid var(--line-strong)", borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => [fmtFull(v), "в день"]}
                  />
                  <Bar dataKey="indie_v7_sum" fill="var(--accent)" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Жанр</th>
                  <th className="r">Игр на радаре</th>
                  <th className="r">Без брендов</th>
                  <th className="r">Горячих</th>
                  <th className="r">Сумма/день</th>
                  <th className="r">Медиана/день</th>
                </tr>
              </thead>
              <tbody>
                {q.data.map((g) => (
                  <tr key={g.genre_id} className="clickable" onClick={() => navigate(`/?genres=${g.genre_id}&max_age=${age}`)}>
                    <td style={{ fontWeight: 600 }}>{g.genre}</td>
                    <td className="r num">{g.games}</td>
                    <td className="r num">
                      {g.indie} <span className="faint">({fmtPct(g.indie_share)})</span>
                    </td>
                    <td className="r num accent">{g.hot || ""}</td>
                    <td className="r num">{fmtN(g.indie_v7_sum)}</td>
                    <td className="r num">{fmtN(g.indie_v7_median)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
