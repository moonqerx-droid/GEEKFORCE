import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";

export function ResetPasswordPage() {
  const [params] = useSearchParams(); const [password, setPassword] = useState(""); const [confirmation, setConfirmation] = useState(""); const [message, setMessage] = useState("");
  return <AuthLayout title="Новый пароль" subtitle="После смены пароля активные сессии будут завершены.">
    <form className="auth-form" onSubmit={async (e) => { e.preventDefault(); const token = params.get("token"); if (!token || password !== confirmation) { setMessage("Проверьте ссылку и совпадение паролей."); return; }
      try { await api.resetPassword(token, password, confirmation); setMessage("Пароль изменён."); } catch { setMessage("Ссылка недействительна или истекла."); } }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <Field label="Новый пароль" name="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <Field label="Повторите пароль" name="confirmation" type="password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
      <button className="auth-submit">Сохранить пароль</button><Link to="/login">Вернуться ко входу</Link>
    </form>
  </AuthLayout>;
}
