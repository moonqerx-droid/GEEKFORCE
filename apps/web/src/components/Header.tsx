import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Headphones, MessageCircleMore } from "lucide-react";
import { api } from "../api/client";
import "./Header.css";

type ApiState = "checking" | "online" | "offline";

export function Header() {
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
        <span className="app-header-logo" aria-hidden="true">H</span>
        <span>HelpFlow</span>
      </Link>
      <nav className="app-header-nav" aria-label="Разделы">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : undefined)}>
          <MessageCircleMore size={16} aria-hidden="true" />
          Сотрудник
        </NavLink>
        <NavLink to="/operator" className={({ isActive }) => (isActive ? "active" : undefined)}>
          <Headphones size={16} aria-hidden="true" />
          Специалист
        </NavLink>
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
    </header>
  );
}
