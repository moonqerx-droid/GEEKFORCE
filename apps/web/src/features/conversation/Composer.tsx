import { useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Button } from "../../components/Button";
import "./Composer.css";

export function Composer({
  busy,
  placeholder,
  onSend,
}: {
  busy: boolean;
  placeholder: string;
  onSend: (content: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    try {
      await onSend(trimmed);
      setValue("");
    } catch {
      // Keep the draft on failure so the user doesn't retype it.
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        className="composer-textarea"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        rows={2}
        maxLength={4000}
        disabled={busy}
        aria-label="Ваше сообщение"
      />
      <Button type="submit" variant="primary" busy={busy} disabled={!value.trim()}>
        Отправить
      </Button>
    </form>
  );
}
