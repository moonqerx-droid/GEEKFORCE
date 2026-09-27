import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [state, setState] = useState("Введите шестизначный код из письма. Он действует 15 минут.");
  const [busy, setBusy] = useState(false);
  const [verified, setVerified] = useState(false);

  return <AuthLayout title="Подтверждение email" subtitle={state}>
    {!verified ? <form className="auth-form" onSubmit={async (event) => {
      event.preventDefault();
      if (!/^\d{6}$/.test(code)) { setState("Введите ровно 6 цифр из письма."); return; }
      setBusy(true);
      try {
        await api.verifyEmail(email, code);
        setVerified(true);
        setState("Email подтверждён. Теперь можно войти.");
      } catch {
        setState("Код недействителен или истёк. Запросите новый код.");
      } finally { setBusy(false); }
    }}>
      <Field label="Email" name="verify_email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
      <Field label="Код из письма" name="verification_code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required />
      <button className="auth-submit" disabled={busy}>{busy ? "Проверяем…" : "Подтвердить email"}</button>
      <button className="auth-link-button" type="button" disabled={!email || busy} onClick={async () => {
        setBusy(true);
        try { await api.resendVerification(email); setState("Новый код отправлен. Проверьте входящие и спам."); }
        catch { setState("Не удалось отправить код. Повторите позже."); }
        finally { setBusy(false); }
      }}>Отправить новый код</button>
    </form> : <Link className="auth-submit auth-button-link" to="/login">Перейти ко входу</Link>}
  </AuthLayout>;
}
