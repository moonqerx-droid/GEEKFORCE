import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { startCooldown, useCooldown } from "../../lib/cooldown";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [refused, setRefused] = useState(false);
  const [busy, setBusy] = useState(false);
  const cooldownKey = `reset:${email.trim().toLowerCase()}`;
  const wait = useCooldown(cooldownKey);
  return <AuthLayout title="Восстановить пароль" subtitle="Если адрес зарегистрирован, мы отправим безопасную ссылку.">
    <form className="auth-form" onSubmit={async (e) => {
      e.preventDefault();
      if (wait > 0 || busy) return;
      setBusy(true); setRefused(false);
      try {
        const answer = await api.forgotPassword(email);
        startCooldown(cooldownKey, answer.retry_after ?? 60);
        setSent(true);
      } catch (error) {
        setRefused(error instanceof ApiError && error.status === 429);
      } finally { setBusy(false); }
    }}>
      {sent ? <div className="auth-message" role="status">Проверьте почту. Ответ одинаков для всех адресов.</div> : null}
      {refused ? <div className="auth-message" role="alert">Слишком много писем за короткое время. Попробуйте через 10 минут.</div> : null}
      <Field label="Email" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <button className="auth-submit" disabled={busy || wait > 0}>
        {wait > 0 ? `Отправить ещё раз через ${wait} с` : sent ? "Отправить ещё раз" : "Отправить ссылку"}
      </button>
    </form>
  </AuthLayout>;
}
