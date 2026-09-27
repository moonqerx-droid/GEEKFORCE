import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { useAuth } from "./AuthProvider";

const DEMO_ACCOUNTS = [
  { label: "Сотрудник", email: "ivan@helpflow.demo" },
  { label: "Специалист", email: "anna@helpflow.demo" },
  { label: "Руководитель", email: "admin@helpflow.demo" },
];
const DEMO_PASSWORD = "DemoPass123";
function serverMessage(error: ApiError): string | null {
  const detail = error.detail as { message?: unknown } | null | undefined;
  return detail && typeof detail.message === "string" ? detail.message : null;
}

const SHOW_DEMO = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_LOGINS === "true";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return <AuthLayout title="Вход" subtitle="Рабочая почта и пароль. Дальше HelpFlow сам откроет нужный раздел.">
    <form className="auth-form" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setMessage("");
      try { await login({ email, password, remember_me: remember }); setMessage("Вход выполнен"); }
      catch (error) {
        const locked = error instanceof ApiError && error.status === 429;
        // A lockout is not a typo: keep the password and say how long to wait.
        if (!locked) setPassword("");
        setMessage(!(error instanceof ApiError) ? "Не удалось связаться с сервером"
          : locked || error.status === 403 ? serverMessage(error) ?? "Сейчас войти нельзя, попробуйте позже"
          : "Неверная почта или пароль");
      }
      finally { setBusy(false); }
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <Field label="Email" name="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="Пароль" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <label className="auth-check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Запомнить меня</label>
      <button className="auth-submit" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
      <div className="auth-links"><Link to="/forgot-password">Забыли пароль?</Link><Link to="/register">Создать аккаунт</Link></div>
    </form>
    {SHOW_DEMO ? (
      <div className="auth-demo-accounts">
        <p>Демо-аккаунты (после <code>python -m app.seed_demo</code>):</p>
        <ul>
          {DEMO_ACCOUNTS.map((account) => (
            <li key={account.email}>
              <button type="button" onClick={() => { setEmail(account.email); setPassword(DEMO_PASSWORD); }}>
                {account.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    ) : null}
  </AuthLayout>;
}
