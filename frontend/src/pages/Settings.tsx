import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { useMe } from "../App";
import { Seg } from "../components/filters";
import { Loader } from "../components/ui";
import { ERROR_TEXT, fmtDate, fmtDateTime } from "../format";

const KIND_LABELS: Record<string, string> = {
  major: "Крупные издатели",
  hc_publisher: "Паблишеры гиперказуала",
  franchise: "Франшизы (слово в названии)",
};

export default function Settings() {
  const me = useMe();
  const [tab, setTab] = useState("team");
  const tabs: [string, string][] = [["team", "Команда"], ["brands", "Бренд-правила"], ["account", "Аккаунт"]];
  if (me.is_superadmin) tabs.push(["platform", "Платформа"]);
  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Настройки</h1>
      </div>
      <div className="tabs">
        {tabs.map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>
      {tab === "team" && <Team />}
      {tab === "brands" && <Brands />}
      {tab === "account" && <Account />}
      {tab === "platform" && <Platform />}
    </>
  );
}

function Team() {
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["team"], queryFn: () => api<any>("/team") });
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () => api<{ url: string }>("/team/invites", { method: "POST", body: { email: email || null } }),
    onSuccess: () => {
      setEmail("");
      qc.invalidateQueries({ queryKey: ["team"] });
    },
    onError: (e) => setError(e instanceof ApiError ? ERROR_TEXT[e.code] || e.code : "Ошибка"),
  });
  const revoke = useMutation({
    mutationFn: (token: string) => api(`/team/invites/${token}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team"] }),
  });
  const toggle = useMutation({
    mutationFn: (u: { id: number; is_active: boolean }) => api(`/team/members/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team"] }),
  });
  if (!q.data) return <Loader />;
  const isOwner = me.role === "owner" || me.is_superadmin;
  return (
    <div className="grid-2">
      <div className="panel panel-pad">
        <h3 className="panel-title">Участники · {q.data.members.length}/{q.data.seats}</h3>
        <table className="data">
          <tbody>
            {q.data.members.map((u: any) => (
              <tr key={u.id}>
                <td>
                  {u.email}
                  {u.name && <span className="muted"> · {u.name}</span>}
                </td>
                <td className="muted">{u.role === "owner" ? "владелец" : "участник"}</td>
                <td className="muted num">{u.last_login ? fmtDateTime(u.last_login) : "не входил"}</td>
                <td className="r">
                  {isOwner && u.id !== me.id && (
                    <button className="btn sm ghost" onClick={() => toggle.mutate(u)}>
                      {u.is_active ? "Отключить" : "Включить"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isOwner && (
        <div className="panel panel-pad">
          <h3 className="panel-title">Пригласить</h3>
          <form
            className="row"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              setError(null);
              invite.mutate();
            }}
          >
            <input className="input" type="email" placeholder="email (необязательно)" value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn primary">Создать ссылку</button>
          </form>
          {error && <div className="error">{error}</div>}
          <div className="stack" style={{ marginTop: 16, gap: 8 }}>
            {q.data.invites.map((i: any) => (
              <div key={i.token} className="panel" style={{ padding: 10, background: "var(--bg)" }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {i.email || "любой email"} · до {fmtDate(i.expires_at)}
                  </span>
                  <span className="row">
                    <button className="btn sm" onClick={() => navigator.clipboard.writeText(i.url)}>Копировать</button>
                    <button className="btn sm ghost" onClick={() => revoke.mutate(i.token)}>Отозвать</button>
                  </span>
                </div>
                <code style={{ display: "block", marginTop: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.url}</code>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Brands() {
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["brand-rules"], queryFn: () => api<{ id: number; kind: string; pattern: string; note: string }[]>("/brand-rules") });
  const [kind, setKind] = useState("major");
  const [pattern, setPattern] = useState("");
  const add = useMutation({
    mutationFn: () => api("/brand-rules", { method: "POST", body: { kind, pattern } }),
    onSuccess: () => {
      setPattern("");
      qc.invalidateQueries({ queryKey: ["brand-rules"] });
    },
  });
  const del = useMutation({
    mutationFn: (id: number) => api(`/brand-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brand-rules"] }),
  });
  if (!q.data) return <Loader />;
  return (
    <div className="stack">
      <div className="banner info">
        Игры этих издателей и франшиз помечаются и по умолчанию скрываются на радаре. Изменения применяются при следующем
        пересчёте (раз в сутки). Автоматические флаги «студия 50M+» и «40+ игр» считаются сами.
      </div>
      {me.is_superadmin && (
        <form
          className="panel panel-pad row"
          onSubmit={(e) => {
            e.preventDefault();
            if (pattern.trim()) add.mutate();
          }}
        >
          <div style={{ width: 420 }}>
            <Seg options={Object.entries(KIND_LABELS) as [string, string][]} value={kind} onChange={setKind} />
          </div>
          <input className="input grow" placeholder={kind === "franchise" ? "слово в названии игры" : "часть имени разработчика"} value={pattern} onChange={(e) => setPattern(e.target.value)} />
          <button className="btn primary">Добавить</button>
        </form>
      )}
      <div className="grid-3">
        {Object.entries(KIND_LABELS).map(([k, label]) => {
          const rules = q.data.filter((r) => r.kind === k);
          return (
            <div key={k} className="panel panel-pad">
              <h3 className="panel-title">
                {label} · {rules.length}
              </h3>
              <div className="chips">
                {rules.map((r) => (
                  <span key={r.id} className="chip" style={{ cursor: "default" }} title={r.note}>
                    {r.pattern}
                    {me.is_superadmin && (
                      <span className="faint" style={{ marginLeft: 6, cursor: "pointer" }} onClick={() => del.mutate(r.id)}>
                        ×
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Account() {
  const [form, setForm] = useState({ current: "", new: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api("/me/password", { method: "POST", body: form }),
    onSuccess: () => {
      setMsg("Пароль изменён");
      setForm({ current: "", new: "" });
    },
    onError: (e) => setMsg(e instanceof ApiError ? ERROR_TEXT[e.code] || "Ошибка" : "Ошибка"),
  });
  return (
    <div className="panel panel-pad" style={{ maxWidth: 420 }}>
      <h3 className="panel-title">Смена пароля</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="field">
          <label className="label">Текущий пароль</label>
          <input className="input" type="password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} required />
        </div>
        <div className="field">
          <label className="label">Новый пароль</label>
          <input className="input" type="password" minLength={8} value={form.new} onChange={(e) => setForm({ ...form, new: e.target.value })} required />
        </div>
        {msg && <p className="muted">{msg}</p>}
        <button className="btn primary">Сохранить</button>
      </form>
    </div>
  );
}

function Platform() {
  const qc = useQueryClient();
  const ws = useQuery({ queryKey: ["workspaces"], queryFn: () => api<any[]>("/admin/workspaces") });
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api<Record<string, { label: string }>>("/plans") });
  const setPlan = useMutation({
    mutationFn: ({ id, plan }: { id: number; plan: string }) => api(`/admin/workspaces/${id}`, { method: "PATCH", body: { plan } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces"] }),
  });
  if (!ws.data || !plans.data) return <Loader />;
  return (
    <div className="stack">
      <div className="banner info">
        Режим SaaS: при <code>GPI_REGISTRATION=open</code> любой может зарегистрироваться и получает тариф <code>GPI_DEFAULT_PLAN</code>.
        Тарифы и лимиты описаны в <code>backend/gpi/plans.py</code>; оплату подключаем позже, она просто меняет тариф команды.
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Команда</th>
              <th className="r">Людей</th>
              <th>Создана</th>
              <th>Тариф</th>
            </tr>
          </thead>
          <tbody>
            {ws.data.map((w) => (
              <tr key={w.id}>
                <td>{w.name}</td>
                <td className="r num">{w.users}</td>
                <td className="muted">{fmtDate(w.created_at)}</td>
                <td style={{ width: 280 }}>
                  <Seg options={Object.entries(plans.data).map(([k, p]) => [k, p.label])} value={w.plan} onChange={(plan) => setPlan.mutate({ id: w.id, plan })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
