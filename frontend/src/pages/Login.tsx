import { FormEvent, ReactNode, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import { ERROR_TEXT } from "../format";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <div className="auth-art">
        <div className="sweep" />
        <span className="blip" style={{ top: "22%", left: "58%" }} />
        <span className="blip" style={{ top: "38%", left: "34%", animationDelay: "1s" }} />
        <span className="blip" style={{ top: "14%", left: "40%", animationDelay: "2s" }} />
        <div style={{ position: "relative" }}>
          <h1>Находим игры, которые растут на органике — раньше остальных.</h1>
          <p>
            Каждый день: топ-чарты 37 стран, свежие релизы, спрос в поиске Google Play. Бренды и закупка трафика отсеяны.
          </p>
        </div>
      </div>
      <div className="auth-form">
        <div className="auth-card">{children}</div>
      </div>
    </div>
  );
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const qc = useQueryClient();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email, password } });
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate(params.get("next") || "/");
    } catch (err) {
      setError(err instanceof ApiError ? ERROR_TEXT[err.code] || "Ошибка входа" : "Сервер недоступен");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <h2>Вход</h2>
      <form onSubmit={submit}>
        <div className="field">
          <label className="label">Email</label>
          <input className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label className="label">Пароль</label>
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "…" : "Войти"}
        </button>
      </form>
      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        Нет аккаунта? <Link className="link" to="/register">Регистрация</Link>
      </p>
    </AuthLayout>
  );
}
