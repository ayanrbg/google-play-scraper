import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, Me, api } from "./api";
import { Loader, RadarMark } from "./components/ui";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Radar from "./pages/Radar";
import GamePage from "./pages/Game";
import Niches from "./pages/Niches";
import NichePage from "./pages/Niche";
import Genres from "./pages/Genres";
import Studios from "./pages/Studios";
import Status from "./pages/Status";
import Settings from "./pages/Settings";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext)!;

function useTheme() {
  const [theme, setTheme] = useState<string | null>(() => {
    try {
      return localStorage.getItem("theme");
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      theme ? localStorage.setItem("theme", theme) : localStorage.removeItem("theme");
    } catch {}
  }, [theme]);
  const isDark = theme ? theme === "dark" : !window.matchMedia("(prefers-color-scheme: light)").matches;
  return { isDark, toggle: () => setTheme(isDark ? "light" : "dark") };
}

export default function App() {
  const location = useLocation();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/me"),
    retry: (n, e) => !(e instanceof ApiError && e.status === 401) && n < 2,
  });

  if (location.pathname === "/login") return <Login />;
  if (location.pathname === "/register") return <Register />;
  if (me.isLoading) return <Loader />;
  if (me.error || !me.data) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;

  return (
    <MeContext.Provider value={me.data}>
      <Shell>
        <Routes>
          <Route path="/" element={<Radar />} />
          <Route path="/game/:id" element={<GamePage />} />
          <Route path="/niches" element={<Niches />} />
          <Route path="/niches/:id" element={<NichePage />} />
          <Route path="/genres" element={<Genres />} />
          <Route path="/studios" element={<Studios />} />
          <Route path="/status" element={<Status />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </MeContext.Provider>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const { isDark, toggle } = useTheme();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [location.pathname]);

  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    qc.clear();
    navigate("/login");
  };

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <RadarMark />
          <div className="brand-name">
            Game Radar
            <small>ideas from Google Play</small>
          </div>
        </div>
        <nav className="nav">
          <div className="nav-section">Поиск идей</div>
          <NavLink to="/" end>
            <span className="nav-dot" /> Радар игр
          </NavLink>
          <NavLink to="/niches">
            <span className="nav-dot" /> Ниши в поиске
          </NavLink>
          <NavLink to="/genres">
            <span className="nav-dot" /> Жанры
          </NavLink>
          <NavLink to="/studios">
            <span className="nav-dot" /> Студии
          </NavLink>
          <div className="nav-section">Система</div>
          <NavLink to="/status">
            <span className="nav-dot" /> Данные
          </NavLink>
          <NavLink to="/settings">
            <span className="nav-dot" /> Настройки
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          <div className="who" title={me.email}>
            {me.email}
            <br />
            <span className="faint">
              {me.workspace.name} · {me.plan.label}
            </span>
          </div>
          <div className="row">
            <button className="btn sm grow" onClick={toggle} title="Сменить тему">
              {isDark ? "☀ Светлая" : "☾ Тёмная"}
            </button>
            <button className="btn sm ghost" onClick={logout}>
              Выйти
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <button className="btn sm menu-toggle" onClick={() => setOpen(!open)}>
          ☰ Меню
        </button>
        {children}
      </main>
    </div>
  );
}
