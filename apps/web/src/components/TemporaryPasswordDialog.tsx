import { useState } from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";
import "./TemporaryPasswordDialog.css";

/**
 * The only place a temporary password ever appears. The caller drops the password
 * from its state in `onDone`, so it cannot be shown again after this closes.
 */
export function TemporaryPasswordDialog({
  name,
  email,
  password,
  reason,
  onDone,
}: {
  name: string;
  email: string;
  password: string;
  reason: "created" | "reset";
  onDone: () => void;
}) {
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  const copyPassword = async () => {
    try {
      await navigator.clipboard.writeText(password);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };

  return (
    <Dialog title="Временный пароль" size="lg">
      <p>
        {reason === "created" ? "Аккаунт готов" : "Пароль сброшен"}: <strong className="temp-who">{name}</strong>
        {" "}<span className="temp-email">({email})</span>. Передайте пароль лично или по защищённому каналу:
        при первом входе человек сразу задаст свой.
      </p>
      <div className="temp-password">
        <code className="temp-password-value" aria-label="Временный пароль, одноразово">{password}</code>
        <Button variant="secondary" onClick={() => void copyPassword()} aria-live="polite">
          {copy === "copied" ? "Скопировано" : "Скопировать"}
        </Button>
      </div>
      {copy === "failed" ? (
        <p className="temp-copy-failed" role="alert">Браузер не дал скопировать. Выделите пароль и скопируйте вручную.</p>
      ) : null}
      <p className="temp-warning" role="note">
        После закрытия пароль больше нельзя будет посмотреть — ни здесь, ни в базе: там хранится только его хеш.
        Если он потеряется, сбросьте пароль ещё раз.
      </p>
      <div className="dialog-actions">
        <Button variant="blue" onClick={onDone} data-autofocus>Готово, пароль передан</Button>
      </div>
    </Dialog>
  );
}
