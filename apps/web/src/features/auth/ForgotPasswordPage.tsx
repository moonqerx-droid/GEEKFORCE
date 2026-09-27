import { useState } from "react";
import { api } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false);
  return <AuthLayout title="Восстановить пароль" subtitle="Если адрес зарегистрирован, мы отправим безопасную ссылку.">
    <form className="auth-form" onSubmit={async (e) => { e.preventDefault(); await api.forgotPassword(email); setSent(true); }}>
      {sent ? <div className="auth-message" role="status">Проверьте почту. Ответ одинаков для всех адресов.</div> : null}
      <Field label="Email" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <button className="auth-submit">Отправить ссылку</button>
    </form>
  </AuthLayout>;
}
