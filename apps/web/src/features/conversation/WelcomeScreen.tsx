import "./WelcomeScreen.css";

const EXAMPLES = [
  "Вчера всё работало, сегодня не могу зайти в рабочую систему с ноутбука, а с телефона открывается. Через 20 минут встреча",
  "Не подключается VPN из дома",
  "Забыл пароль от почты",
  "Нужен доступ к папке отдела на общем диске",
];

const PROMISES = [
  ["Своими словами", "Названия систем и категории знать не нужно."],
  ["Только нужные вопросы", "Если ответ уже есть в тексте, переспрашивать не будем."],
  ["Без пересказа", "Если понадобится человек, он получит всю историю сразу."],
] as const;

/** The empty chat: what to write and why it is safe to write it plainly. The composer sits below. */
export function WelcomeScreen({ firstName, onExample }: { firstName?: string; onExample: (text: string) => void }) {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <p className="welcome-greeting">{firstName ? `${firstName}, привет!` : "Привет!"}</p>
      <h1 id="welcome-title" className="welcome-title">Что случилось?</h1>
      <p className="welcome-lead">
        Расскажите, как коллеге, и приложите скриншот ошибки, если он есть. Дальше разберёмся вместе, по шагам.
      </p>
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
