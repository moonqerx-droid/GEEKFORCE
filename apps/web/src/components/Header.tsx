import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { LogOut } from "lucide-react";
import { api } from "../api/client";
import type { UserRole } from "../api/types";
import { ROLE_LABEL, homePathFor } from "../lib/labels";
import { Avatar } from "./primitives";
import "./Header.css";

const NAV: Record<UserRole, { to: string; label: string; end?: boolean }[]> = {
  employee: [
    { to: "/employee?new=1", label: "Новое обращение", end: true },
    { to: "/employee/history", label: "Мои обращения" },
  ],
  operator: [{ to: "/operator", label: "Обращения" }],
  admin: [
    { to: "/admin", label: "Обзор", end: true },
    { to: "/operator", label: "Обращения" },
    { to: "/admin/team", label: "Пользователи" },
  ],
};

interface HeaderProps {
  role: UserRole;
  name: string;
  onLogout: () => void | Promise<void>;
}

export function Header({ role, name, onLogout }: HeaderProps) {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api.health()
        .then(() => { if (!cancelled) setOffline(false); })
        .catch(() => { if (!cancelled) setOffline(true); });
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
      <Link to={homePathFor(role)} className="app-header-brand">
        <img className="app-header-logo" src="/brand/helpflow-mark.svg" alt="" aria-hidden="true" />
        <span>HelpFlow</span>
      </Link>
      <nav className="app-header-nav" aria-label="Разделы">
        {NAV[role].map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}
            className={({ isActive }) => (isActive ? "active" : undefined)}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      {offline ? <span className="app-header-offline" role="status">Нет связи с сервером</span> : null}
      <NavLink to="/profile" className={({ isActive }) => `app-header-user ${isActive ? "active" : ""}`} aria-label={`Профиль: ${name}`}>
        <Avatar kind={role === "employee" ? "employee" : "human"} name={name} size={30} />
        <span className="app-header-user-text">
          <span className="app-header-user-name">{name}</span>
          <span className="app-header-user-role">{ROLE_LABEL[role]}</span>
        </span>
      </NavLink>
      <button type="button" className="app-header-logout" onClick={() => void onLogout()} aria-label="Выйти">
        <LogOut size={17} aria-hidden="true" />
      </button>
    </header>
  );
}
