import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type { Department, RegistrationPayload } from "../../api/types";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { validateRegistration, type RegistrationErrors } from "./validation";

type OperatorForm = Omit<RegistrationPayload, "accepted_terms">;

const initial: OperatorForm = {
  first_name: "",
  last_name: "",
  email: "",
  department: "",
  password: "",
  password_confirmation: "",
};

export function OperatorRegisterPage() {
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get("invite") ?? "";
  const [value, setValue] = useState(initial);
  const [errors, setErrors] = useState<RegistrationErrors>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const change = (key: keyof OperatorForm, next: string) => {
    setValue((current) => ({ ...current, [key]: next }));
  };

  return <AuthLayout title="Регистрация специалиста" subtitle="Создайте отдельный аккаунт специалиста по персональному приглашению.">
    {!inviteToken ? <div className="auth-message" role="alert">Ссылка приглашения недействительна: в ней отсутствует токен.</div> : null}
    <form className="auth-form" noValidate onSubmit={async (event) => {
      event.preventDefault();
      const payload: RegistrationPayload = { ...value, accepted_terms: true };
      const nextErrors = validateRegistration(payload);
      setErrors(nextErrors);
      if (!inviteToken || Object.keys(nextErrors).length) return;
      setBusy(true);
      setMessage("");
      try {
        await api.registerOperator({ ...value, invite_token: inviteToken });
        setMessage("Аккаунт специалиста создан. Проверьте письмо и подтвердите email.");
      } catch {
        setMessage("Не удалось завершить регистрацию. Проверьте приглашение и введённые данные.");
      } finally {
        setBusy(false);
      }
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <div className="auth-name-row">
        <Field label="Имя" name="operator_first_name" value={value.first_name} error={errors.first_name} onChange={(event) => change("first_name", event.target.value)} />
        <Field label="Фамилия" name="operator_last_name" value={value.last_name} error={errors.last_name} onChange={(event) => change("last_name", event.target.value)} />
      </div>
      <Field label="Рабочий email" name="operator_email" type="email" value={value.email} error={errors.email} onChange={(event) => change("email", event.target.value)} />
      <label className="auth-field"><span>Отдел</span><select aria-label="Отдел" value={value.department} aria-invalid={Boolean(errors.department)} onChange={(event) => change("department", event.target.value as Department)}>
        <option value="">Выберите отдел</option><option value="it">IT</option><option value="sales">Продажи</option><option value="marketing">Маркетинг</option><option value="finance">Финансы</option><option value="hr">HR</option><option value="operations">Операционный отдел</option><option value="other">Другое</option>
      </select>{errors.department ? <small className="auth-field-error">{errors.department}</small> : null}</label>
      <Field label="Пароль" name="operator_password" type="password" value={value.password} error={errors.password} onChange={(event) => change("password", event.target.value)} />
      <Field label="Повторите пароль" name="operator_password_confirmation" type="password" value={value.password_confirmation} error={errors.password_confirmation} onChange={(event) => change("password_confirmation", event.target.value)} />
      <button className="auth-submit" disabled={busy || !inviteToken}>{busy ? "Создаём…" : "Создать аккаунт специалиста"}</button>
    </form>
  </AuthLayout>;
}
