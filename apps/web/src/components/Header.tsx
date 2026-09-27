import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Headphones, LogOut, MessageCircleMore } from "lucide-react";
import { api } from "../api/client";
import "./Header.css";

type ApiState = "checking" | "online" | "offline";

interface HeaderProps {
  role: "employee" | "operator";
  name: string;
  onLogout: () => void | Promise<void>;
}

export function Header({ role, name, onLogout }: HeaderProps) {
  const [apiState, setApiState] = useState<ApiState>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api
        .health()
        .then(() => {
          if (!cancelled) setApiState("online");
        })
        .catch(() => {
          if (!cancelled) setApiState("offline");
        });
    };
    check();
    const interval = window.setInterval(check, 20000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <header className="app-header">
      <Link to="/" className="app-header-brand">
        <img className="app-header-logo" src="/brand/helpflow-logo-512.png" alt="" aria-hidden="true" />
        <span>HelpFlow</span>
      </Link>
      <nav className="app-header-nav" aria-label="Разделы">
        {role === "employee" ? <>
          <NavLink to="/employee" end className={({ isActive }) => (isActive ? "active" : undefined)}>
            <MessageCircleMore size={16} aria-hidden="true" />Мои обращения
          </NavLink>
          <NavLink to="/employee/history" className={({ isActive }) => (isActive ? "active" : undefined)}>История</NavLink>
        </> : <NavLink to="/operator" className={({ isActive }) => (isActive ? "active" : undefined)}>
          <Headphones size={16} aria-hidden="true" />Очередь
        </NavLink>}
      </nav>
      <span
        className={`api-indicator api-indicator-${apiState}`}
        role="status"
        title={
          apiState === "online"
            ? "Сервер доступен"
            : apiState === "offline"
              ? "Сервер недоступен"
              : "Проверка соединения"
        }
      >
        <span className="api-indicator-dot" aria-hidden="true" />
        {apiState === "online" ? "Онлайн" : apiState === "offline" ? "Нет связи" : "Проверка…"}
      </span>
      <span className="app-header-user">{name}</span>
      <button type="button" className="app-header-logout" onClick={() => void onLogout()} aria-label="Выйти">
        <LogOut size={17} aria-hidden="true" />
      </button>
    </header>
  );
}
