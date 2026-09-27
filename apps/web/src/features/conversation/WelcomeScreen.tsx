import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "../../components/Button";
import "./WelcomeScreen.css";

const EXAMPLES = [
  "Вчера всё работало, сегодня не могу зайти в рабочую систему с ноутбука, а с телефона открывается. Через 20 минут встреча",
  "Не подключается VPN из дома",
  "Забыл пароль от почты",
  "Нужен доступ к папке отдела на общем диске",
];

export function WelcomeScreen({
  busy,
  onSubmit,
  firstName,
}: {
  busy: boolean;
  onSubmit: (content: string) => Promise<void>;
  firstName?: string;
}) {
  const [value, setValue] = useState("");

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    await onSubmit(trimmed);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <p className="welcome-greeting">{firstName ? `${firstName}, привет!` : "Привет!"}</p>
      <h1 id="welcome-title" className="welcome-title">Что случилось?</h1>
      <p className="welcome-lead">
        Расскажите своими словами, как коллеге. Названия систем и категории знать не нужно — разберёмся вместе.
      </p>

      <form className="welcome-form" onSubmit={submit}>
        <label htmlFor="welcome-input" className="visually-hidden">Опишите проблему</label>
        <textarea
          id="welcome-input"
          className="welcome-input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Например: не открывается почта, пишет «нет подключения»…"
          rows={4}
          maxLength={4000}
          autoFocus
        />
        <div className="welcome-form-bar">
          <span className="welcome-form-hint">Enter — отправить, Shift+Enter — новая строка</span>
          <Button type="submit" variant="primary" busy={busy} disabled={!value.trim()}>
            Отправить
          </Button>
        </div>
      </form>

      <div className="welcome-examples">
        <p className="welcome-examples-title">Или начните с похожей ситуации</p>
        <div className="welcome-chips">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="welcome-chip" onClick={() => setValue(example)}>
              {example}
            </button>
          ))}
        </div>
      </div>

      <p className="welcome-promise">
        Если сами не справимся, обращение уйдёт специалисту вместе со всем, что вы уже рассказали.
        Повторять ничего не придётся.
      </p>
    </section>
  );
}
