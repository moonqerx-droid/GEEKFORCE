import type { Dispatch, FormEvent, KeyboardEvent, SetStateAction } from "react";
import { Button } from "../../components/Button";
import "./Composer.css";

export function Composer({
  busy,
  placeholder,
  onSend,
  value,
  onValueChange,
}: {
  busy: boolean;
  placeholder: string;
  onSend: (content: string) => Promise<void>;
  value: string;
  onValueChange: Dispatch<SetStateAction<string>>;
}) {
  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    onValueChange("");
    try {
      await onSend(trimmed);
    } catch {
      // Restore the failed draft unless the user already started the next message.
      onValueChange((current) => current.trim() ? current : trimmed);
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
        onChange={(event) => onValueChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        rows={2}
        maxLength={4000}
        aria-label="Ваше сообщение"
      />
      <Button type="submit" variant="primary" busy={busy} disabled={!value.trim()}>
        Отправить
      </Button>
    </form>
  );
}
