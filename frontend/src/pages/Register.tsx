import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { ERROR_TEXT } from "../format";
import { AuthLayout } from "./Login";

export default function Register() {
  const [params] = useSearchParams();
  const invite = params.get("invite");
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api<{ registration: string }>("/auth/config") });
  const inv = useQuery({
    queryKey: ["invite", invite],
    queryFn: () => api<{ workspace: string; email: string | null }>(`/auth/invite/${invite}`),
    enabled: !!invite,
    retry: false,
  });
  const [form, setForm] = useState({ email: "", password: "", name: "", workspace_name: "" });
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const closed = !invite && cfg.data?.registration !== "open";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/register", {
        method: "POST",
        body: { ...form, email: form.email || inv.data?.email, invite: invite || undefined },
      });
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? ERROR_TEXT[err.code] || "Не удалось зарегистрироваться" : "Сервер недоступен");
    }
  };

  return (
    <AuthLayout>
      <h2>Регистрация</h2>
      {invite && inv.data && (
        <p className="muted" style={{ marginTop: -8 }}>
          Приглашение в команду <b style={{ color: "var(--text)" }}>{inv.data.workspace}</b>
        </p>
      )}
      {invite && inv.isError && <div className="error">{ERROR_TEXT.invite_invalid}</div>}
      {closed ? (
        <p className="muted">Регистрация только по приглашению. Попросите ссылку у владельца команды.</p>
      ) : (
        <form onSubmit={submit}>
          <div className="field">
            <label className="label">Имя</label>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="field">
            <label className="label">Email</label>
            <input
              className="input"
              type="email"
              required={!inv.data?.email}
              placeholder={inv.data?.email || ""}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="field">
            <label className="label">Пароль (от 8 символов)</label>
            <input className="input" type="password" minLength={8} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          {!invite && (
            <div className="field">
              <label className="label">Название команды</label>
              <input className="input" value={form.workspace_name} onChange={(e) => setForm({ ...form, workspace_name: e.target.value })} />
            </div>
          )}
          {error && <div className="error">{error}</div>}
          <button className="btn primary" style={{ width: "100%" }}>
            Создать аккаунт
          </button>
        </form>
      )}
      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        Уже есть аккаунт? <Link className="link" to="/login">Войти</Link>
      </p>
    </AuthLayout>
  );
}
