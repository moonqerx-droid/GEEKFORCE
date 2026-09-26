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
      <h1 className="welcome-title">Опишите проблему своими словами</h1>
      <p className="welcome-subtitle">
        HelpFlow разберётся, что случилось, задаст нужные уточнения и поможет решить проблему
        шаг за шагом — или сразу передаст специалисту.
      </p>

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
          disabled={busy}
          aria-label="Описание проблемы"
        />
        <Button type="submit" variant="primary" size="lg" busy={busy} disabled={!value.trim()}>
          Отправить обращение
        </Button>
      </form>

      <div className="welcome-examples">
        <p className="welcome-examples-label">Или выберите пример:</p>
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
