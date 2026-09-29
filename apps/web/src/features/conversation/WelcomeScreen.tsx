import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { KnownIssue } from "../../api/types";
import { formatTime } from "../../lib/labels";
import "./WelcomeScreen.css";

const EXAMPLES = [
  "Вчера всё работало, сегодня не могу зайти в рабочую систему с ноутбука, а с телефона открывается. Через 20 минут встреча",
  "Не подключается VPN из дома",
  "Забыл пароль от почты",
  "Нужен доступ к папке отдела на общем диске",
];

export const ABILITIES_QUESTION = "Что ты умеешь?";

const PROMISES = [
  ["Своими словами", "Названия систем и категории знать не нужно."],
  ["Только нужные вопросы", "Если ответ уже есть в тексте, переспрашивать не будем."],
  ["Без пересказа", "Если понадобится человек, он получит всю историю сразу."],
] as const;

/** The empty chat: what to write and why it is safe to write it plainly. The composer sits below. */
export function WelcomeScreen({
  firstName,
  onExample,
  onReport,
  onAsk,
}: {
  firstName?: string;
  onExample: (text: string) => void;
  /** Sends a question to the assistant at once: «Что ты умеешь?» shows every topic it covers. */
  onAsk?: (text: string) => void;
  /** Starts a request right away; the radar adds it to the outage, so the employee hears when it is fixed. */
  onReport?: (text: string) => void;
}) {
  const [issues, setIssues] = useState<KnownIssue[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    // A status line is a bonus: if it cannot load, the page simply goes without it.
    api.knownIssues(controller.signal).then(setIssues).catch(() => undefined);
    return () => controller.abort();
  }, []);

  return (
    <section className="welcome" aria-labelledby="welcome-title">
      {issues.length ? (
        <section className="known-issues" aria-label="Известные сбои">
          {issues.map((issue) => (
            <article key={issue.id} className="known-issue">
              <span className="known-issue-dot" aria-hidden="true" />
              <div className="known-issue-body">
                <h2 className="known-issue-title">{issue.service}: известный сбой, уже чиним</h2>
                <p className="known-issue-text">
                  С {formatTime(issue.since)}, затронуто сотрудников: {issue.affected}.
                  {issue.update ? ` Последнее от поддержки: «${issue.update}»` : " Писать отдельно не нужно — сообщим, когда починят."}
                </p>
              </div>
              {onReport ? (
                <button type="button" className="known-issue-join" onClick={() => onReport(`У меня тоже не работает ${issue.service}`)}>
                  У меня то же самое
                </button>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}
      <p className="welcome-greeting">{firstName ? `${firstName}, привет!` : "Привет!"}</p>
      <h1 id="welcome-title" className="welcome-title">Что случилось?</h1>
      <p className="welcome-lead">
        Расскажите, как коллеге, и приложите скриншот ошибки, если он есть. Дальше разберёмся вместе, по шагам.
      </p>
      {onAsk ? (
        <p className="welcome-abilities">
          <button type="button" className="welcome-abilities-button" onClick={() => onAsk(ABILITIES_QUESTION)}>
            Что ты умеешь?
          </button>
          <span>Покажу, с какими проблемами помогаю и на какие вопросы о правилах компании отвечаю.</span>
        </p>
      ) : null}
      <ul className="welcome-promises">
        {PROMISES.map(([title, text]) => (
          <li key={title}><strong>{title}</strong><span>{text}</span></li>
        ))}
      </ul>
      <div className="welcome-examples">
        <p className="welcome-examples-title">Похожие ситуации, чтобы начать</p>
        <div className="welcome-chips">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="welcome-chip" onClick={() => onExample(example)}>
              {example}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
