import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { useAuth } from "./AuthProvider";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return <AuthLayout title="Войти в HelpFlow" subtitle="Используйте рабочий email — кабинет откроется согласно вашей роли.">
    <form className="auth-form" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setMessage("");
      try { await login({ email, password, remember_me: remember }); setMessage("Вход выполнен"); }
      catch (error) { setPassword(""); setMessage(error instanceof ApiError ? "Проверьте email и пароль" : "Не удалось связаться с сервером"); }
      finally { setBusy(false); }
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <Field label="Email" name="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="Пароль" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <label className="auth-check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Запомнить меня</label>
      <button className="auth-submit" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
      <div className="auth-links"><Link to="/forgot-password">Забыли пароль?</Link><Link to="/register">Создать аккаунт</Link></div>
    </form>
  </AuthLayout>;
}
