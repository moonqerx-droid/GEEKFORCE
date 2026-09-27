import { useState, type FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { PASSWORD_RULES, validateNewPassword, type PasswordErrors } from "../../lib/password";
import "./ChangePasswordForm.css";

function serverMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail as { message?: unknown } | null | undefined;
    if (detail && typeof detail.message === "string") return detail.message;
    if (error.status === 422) return PASSWORD_RULES;
  }
  return "Не удалось сменить пароль. Попробуйте ещё раз.";
}

export function ChangePasswordForm({
  name,
  currentLabel = "Текущий пароль",
  submitLabel = "Сменить пароль",
  successMessage = "Пароль изменён. Другие сеансы завершены.",
  onChanged,
}: {
  name: string;
  currentLabel?: string;
  submitLabel?: string;
  successMessage?: string | null;
  onChanged?: () => Promise<void> | void;
}) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [failure, setFailure] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setDone(false);
    setFailure("");
    const nextErrors = validateNewPassword(current, password, confirmation);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setBusy(true);
    try {
      await api.changePassword({ current_password: current, password, password_confirmation: confirmation });
      setCurrent("");
      setPassword("");
      setConfirmation("");
      setDone(true);
      await onChanged?.();
    } catch (error) {
      setFailure(serverMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const field = (id: keyof PasswordErrors, label: string, value: string, onChange: (next: string) => void, autoComplete: string) => (
    <div className="pw-field">
      <label htmlFor={`pw-${id}`}>{label}</label>
      <input
        id={`pw-${id}`}
        type="password"
        value={value}
        autoComplete={autoComplete}
        aria-invalid={Boolean(errors[id])}
        aria-describedby={errors[id] ? `pw-${id}-error` : id === "password" ? "pw-rules" : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {errors[id] ? <small id={`pw-${id}-error`} className="pw-error">{errors[id]}</small> : null}
    </div>
  );

  return (
    <form className="pw-form" aria-label={name} noValidate onSubmit={submit}>
      {field("current_password", currentLabel, current, setCurrent, "current-password")}
      {field("password", "Новый пароль", password, setPassword, "new-password")}
      {!errors.password ? <small id="pw-rules" className="pw-hint">{PASSWORD_RULES}</small> : null}
      {field("password_confirmation", "Повторите новый пароль", confirmation, setConfirmation, "new-password")}
      {failure ? <p className="pw-failure" role="alert">{failure}</p> : null}
      {done && successMessage ? <p className="pw-done" role="status">{successMessage}</p> : null}
      <div>
        <Button type="submit" variant="blue" busy={busy}>{submitLabel}</Button>
      </div>
    </form>
  );
}
