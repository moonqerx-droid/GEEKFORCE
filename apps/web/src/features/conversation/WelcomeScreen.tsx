import { useState } from "react";
import { Button } from "../../components/Button";
import "./WelcomeScreen.css";

const EXAMPLES = [
  "Не могу войти в CRM с ноутбука, но с телефона работает. Через 20 минут встреча.",
  "Не открывается корпоративная почта, пишет ошибку авторизации.",
  "Не подключается VPN из дома, вчера всё работало.",
  "Пришла подозрительная ссылка в письме, боюсь что это фишинг.",
];

interface WelcomeScreenProps {
  busy: boolean;
  onSubmit: (content: string) => void;
}

export function WelcomeScreen({ busy, onSubmit }: WelcomeScreenProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    onSubmit(trimmed);
  };

  return (
    <div className="welcome">
      <div className="welcome-intro">
        <p className="welcome-product-line">IT-помощник вашей команды</p>
        <h1 className="welcome-title">Расскажите, что сломалось. Дальше разберёмся вместе.</h1>
        <p className="welcome-subtitle">
          HelpFlow уточнит детали, предложит безопасные шаги и подключит специалиста,
          если автоматической помощи окажется недостаточно.
        </p>
        <div className="welcome-promises" aria-label="Как работает HelpFlow">
          <span>Понимает контекст</span>
          <span>Ведёт по шагам</span>
          <span>Не теряет историю</span>
        </div>
      </div>

      <form
        className="welcome-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          className="welcome-textarea"
          placeholder="Например: не могу войти в CRM с ноутбука…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={4}
          maxLength={4000}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          disabled={busy}
          aria-label="Описание проблемы"
        />
        <Button type="submit" variant="primary" size="lg" busy={busy} disabled={!value.trim()}>
          Начать диалог
        </Button>
      </form>

      <div className="welcome-examples">
        <p className="welcome-examples-label">Можно начать с готового примера</p>
        <div className="welcome-examples-list">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="welcome-example-chip"
              onClick={() => onSubmit(example)}
              disabled={busy}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
