import { createContext, useContext, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, Me, api } from "./api";
import { BrandMark, Loader } from "./components/ui";
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

// The site is public: `null` is a guest who can read everything. Signing in adds team features
// (marks, saved views, settings) and admin tools.
const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
/** For pages that exist only for signed-in users (the route sends guests to /login). */
export const useUser = () => useContext(MeContext)!;

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
    const dark = theme ? theme === "dark" : !window.matchMedia("(prefers-color-scheme: light)").matches;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0a110f" : "#f1eee5");
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
  const user = me.data ?? null;

  return (
    <MeContext.Provider value={user}>
      <Shell>
        <Routes>
          <Route path="/" element={<Radar />} />
          <Route path="/game/:id" element={<GamePage />} />
          <Route path="/niches" element={<Niches />} />
          <Route path="/niches/:id" element={<NichePage />} />
          <Route path="/genres" element={<Genres />} />
          <Route path="/studios" element={<Studios />} />
          <Route path="/status" element={<Status />} />
          <Route path="/settings" element={user ? <Settings /> : <Navigate to="/login?next=/settings" replace />} />
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
  const navType = useNavigationType();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(false);
    // a new page starts at the top; Back keeps the browser's scroll position
    if (navType !== "POP") window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", esc);
    document.body.classList.add("locked");
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.classList.remove("locked");
    };
  }, [open]);

  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    qc.clear();
    navigate("/");
  };

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <BrandMark />
          <div className="brand-name">
            PlayTrend
            <small>game trends on Google Play</small>
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
          {me && (
            <NavLink to="/settings">
              <span className="nav-dot" /> Настройки
            </NavLink>
          )}
        </nav>
        <div className="sidebar-foot">
          {me && (
            <div className="who" title={me.email}>
              {me.email}
              <br />
              <span className="faint">
                {me.workspace.name} · {me.plan.label}
              </span>
            </div>
          )}
          <div className="row">
            <button className="btn sm grow" onClick={toggle} title="Сменить тему">
              {isDark ? "☀ Светлая" : "☾ Тёмная"}
            </button>
            {me ? (
              <button className="btn sm ghost" onClick={logout}>
                Выйти
              </button>
            ) : (
              <Link className="btn sm ghost" to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} title="Вход для команды: отметки, заметки, сохранённые фильтры">
                Войти
              </Link>
            )}
          </div>
        </div>
      </aside>
      {open && <div className="backdrop" onClick={() => setOpen(false)} />}
      <main className="main">{children}</main>
      <nav className="tabbar">
        <NavLink to="/" end>
          <TabIcon d={<><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-5" /></>} />
          Радар
        </NavLink>
        <NavLink to="/niches">
          <TabIcon d={<><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></>} />
          Ниши
        </NavLink>
        <NavLink to="/genres">
          <TabIcon d={<path d="M5 20v-8M12 20V5M19 20v-5" />} />
          Жанры
        </NavLink>
        <NavLink to="/studios">
          <TabIcon d={<><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>} />
          Студии
        </NavLink>
        <button className={open || ["/status", "/settings"].includes(location.pathname) ? "active" : ""} onClick={() => setOpen(!open)}>
          <TabIcon d={<path d="M4 7h16M4 12h16M4 17h16" />} />
          Ещё
        </button>
      </nav>
    </div>
  );
}

function TabIcon({ d }: { d: React.ReactNode }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {d}
    </svg>
  );
}
