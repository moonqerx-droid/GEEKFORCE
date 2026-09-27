import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "../../components/primitives";
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
          <h1>Поддержка, которая не бесит</h1>
          <p className="auth-story-lead">
            Пишете как есть — помощник разбирается, что случилось, насколько срочно, и ведёт к решению по шагам.
            Если нужен человек, он получит всю историю сразу.
          </p>
        </div>
        <div className="auth-demo" aria-hidden="true">
          <div className="auth-demo-user">
            У меня опять всё сломалось. С телефона CRM открывается, с ноутбука нет. Через 20 минут встреча!
          </div>
          <div className="auth-demo-reply">
            <Avatar kind="assistant" size={28} />
            <div className="auth-demo-card">
              <span className="auth-demo-chip auth-demo-chip-urgent">Срочно: встреча через 20 минут</span>
              <span className="auth-demo-chip">CRM, вход только с ноутбука</span>
              <p>Раз с телефона работает, дело в ноутбуке. Начнём с самого быстрого шага.</p>
            </div>
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
