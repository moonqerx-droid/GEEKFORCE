import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import "./AuthLayout.css";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <main className="auth-shell">
      <section className="auth-story" aria-label="О HelpFlow">
        <Link to="/" className="auth-brand">
          <img src="/brand/helpflow-logo-512.png" alt="" />
          <span>HelpFlow</span>
        </Link>
        <div className="auth-story-copy">
          <p className="auth-kicker">Поддержка без потерянного контекста</p>
          <h1>От вопроса сотрудника — к понятному решению.</h1>
          <div className="auth-route" aria-hidden="true">
            <span>Сообщение</span><i /><span>Диагностика</span><i /><span>Специалист</span>
          </div>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-form-wrap">
          <h2>{title}</h2>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
        </div>
      </section>
    </main>
  );
}
