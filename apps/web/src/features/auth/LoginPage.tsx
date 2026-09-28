import { useState } from "react";
import { Link } from "react-router-dom";
import { ChartColumn, Headset, MessageCircle } from "lucide-react";
import { ApiError } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { useAuth } from "./AuthProvider";

/** Seeded by `python -m app.seed_demo`; one click signs in, so a demo shows every role in seconds. */
const DEMO_ACCOUNTS = [
  { role: "сотрудник", title: "Сотрудник", person: "Иван Петров", what: "Пишет о проблеме, помощник ведёт по шагам", email: "ivan@helpflow.demo", Icon: MessageCircle },
  { role: "специалист", title: "Специалист", person: "Анна Смирнова", what: "Очередь, карточка обращения, ответ в том же чате", email: "anna@helpflow.demo", Icon: Headset },
  { role: "руководитель", title: "Руководитель поддержки", person: "Администратор", what: "Метрики, команда и база знаний", email: "admin@helpflow.demo", Icon: ChartColumn },
];
const DEMO_PASSWORD = "DemoPass123";
function serverMessage(error: ApiError): string | null {
  const detail = error.detail as { message?: unknown } | null | undefined;
  return detail && typeof detail.message === "string" ? detail.message : null;
}

// On by default for the demo build; set VITE_SHOW_DEMO_LOGINS=false for a real deployment.
const SHOW_DEMO = import.meta.env.VITE_SHOW_DEMO_LOGINS !== "false";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const signIn = async (address: string, secret: string, demo = false) => {
    setBusy(true); setMessage("");
    try { await login({ email: address, password: secret, remember_me: remember }); setMessage("Вход выполнен"); }
    catch (error) {
      const locked = error instanceof ApiError && error.status === 429;
      // A lockout is not a typo: keep the password and say how long to wait.
      if (!locked) setPassword("");
      setMessage(!(error instanceof ApiError) ? "Не удалось связаться с сервером"
        : locked || error.status === 403 ? serverMessage(error) ?? "Сейчас войти нельзя, попробуйте позже"
        : demo ? "Демо-аккаунта нет в базе: загрузите демо-данные командой python -m app.seed_demo"
        : "Неверная почта или пароль");
    }
    finally { setBusy(false); }
  };
  return <AuthLayout title="Вход" subtitle="Рабочая почта и пароль. Дальше HelpFlow сам откроет нужный раздел.">
    <form className="auth-form" onSubmit={(event) => {
      event.preventDefault();
      void signIn(email, password);
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <Field label="Email" name="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="Пароль" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <label className="auth-check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Запомнить меня</label>
      <button className="auth-submit" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
      <div className="auth-links"><Link to="/forgot-password">Забыли пароль?</Link><Link to="/register">Создать аккаунт</Link></div>
    </form>
    {SHOW_DEMO ? (
      <section className="auth-quick" aria-labelledby="auth-quick-title">
        <h2 id="auth-quick-title" className="auth-quick-title">Быстрый вход</h2>
        <p className="auth-quick-text">Демо-аккаунты: посмотрите HelpFlow глазами каждой роли.</p>
        <ul className="auth-quick-list">
          {DEMO_ACCOUNTS.map(({ Icon, ...account }) => (
            <li key={account.email}>
              <button type="button" className="auth-quick-role" disabled={busy}
                aria-label={`Войти как ${account.role}: ${account.person}`}
                onClick={() => { setEmail(account.email); setPassword(DEMO_PASSWORD); void signIn(account.email, DEMO_PASSWORD, true); }}>
                <span className="auth-quick-icon" aria-hidden="true"><Icon size={18} /></span>
                <span className="auth-quick-body">
                  <span className="auth-quick-name">{account.title}</span>
                  <span className="auth-quick-what">{account.what}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    ) : null}
  </AuthLayout>;
}
