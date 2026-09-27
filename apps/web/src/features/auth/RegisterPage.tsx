import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ConflictError } from "../../api/client";
import type { RegistrationPayload } from "../../api/types";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { validateRegistration, type RegistrationErrors } from "./validation";

const initial: RegistrationPayload = { first_name: "", last_name: "", email: "", department: "", password: "", password_confirmation: "", accepted_terms: false };

export function RegisterPage() {
  const navigate = useNavigate();
  const [value, setValue] = useState(initial);
  const [errors, setErrors] = useState<RegistrationErrors>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const change = (key: keyof RegistrationPayload, next: string | boolean) => setValue((current) => ({ ...current, [key]: next }));
  return <AuthLayout title="Создать аккаунт" subtitle="Для сотрудников компании. Специалист входит по персональному приглашению.">
    <form className="auth-form" noValidate onSubmit={async (event) => {
      event.preventDefault(); const nextErrors = validateRegistration(value); setErrors(nextErrors);
      if (Object.keys(nextErrors).length) return;
      setBusy(true); setMessage("");
      try {
        await api.register(value);
        setMessage("Аккаунт создан. Код подтверждения отправлен на email.");
        navigate(`/verify-email?email=${encodeURIComponent(value.email)}`);
      }
      catch (error) {
        if (error instanceof ConflictError) {
          navigate(`/verify-email?email=${encodeURIComponent(value.email)}`);
        } else {
          setMessage("Не удалось завершить регистрацию. Проверьте данные или повторите позже.");
        }
      }
      finally { setBusy(false); }
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <div className="auth-name-row">
        <Field label="Имя" name="first_name" value={value.first_name} error={errors.first_name} onChange={(e) => change("first_name", e.target.value)} />
        <Field label="Фамилия" name="last_name" value={value.last_name} error={errors.last_name} onChange={(e) => change("last_name", e.target.value)} />
      </div>
      <Field label="Рабочий email" name="email" type="email" value={value.email} error={errors.email} onChange={(e) => change("email", e.target.value)} />
      <label className="auth-field"><span>Отдел</span><select value={value.department} aria-invalid={Boolean(errors.department)} onChange={(e) => change("department", e.target.value)}>
        <option value="">Выберите отдел</option><option value="it">IT</option><option value="sales">Продажи</option><option value="marketing">Маркетинг</option><option value="finance">Финансы</option><option value="hr">HR</option><option value="operations">Операционный отдел</option><option value="other">Другое</option>
      </select>{errors.department ? <small className="auth-field-error">{errors.department}</small> : null}</label>
      <Field label="Пароль" name="password" type="password" value={value.password} error={errors.password} onChange={(e) => change("password", e.target.value)} />
      <Field label="Повторите пароль" name="password_confirmation" type="password" value={value.password_confirmation} error={errors.password_confirmation} onChange={(e) => change("password_confirmation", e.target.value)} />
      <label className="auth-check"><input type="checkbox" checked={value.accepted_terms} onChange={(e) => change("accepted_terms", e.target.checked)} /> Согласен с правилами обработки данных</label>
      {errors.accepted_terms ? <small className="auth-field-error">{errors.accepted_terms}</small> : null}
      <button className="auth-submit" disabled={busy}>{busy ? "Создаём…" : "Создать аккаунт"}</button>
      <div className="auth-links"><Link to="/login">Уже есть аккаунт</Link></div>
    </form>
  </AuthLayout>;
}
