import { useState } from "react";
import { Link } from "react-router-dom";
import { ChartColumn, Headset, MessageCircle } from "lucide-react";
import { ApiError } from "../../api/client";
import { AuthLayout } from "./AuthLayout";
import { Field } from "./Field";
import { useAuth } from "./AuthProvider";
import { rememberScenario } from "../../lib/scenario";

/** Seeded by `python -m app.seed_demo`; one click signs in, so a demo shows every role in seconds. */
const DEMO_ACCOUNTS = [
  { role: "сотрудник", title: "Сотрудник", person: "Иван Петров", what: "Пишет о проблеме, помощник ведёт по шагам", email: "ivan@helpflow.demo", Icon: MessageCircle },
  { role: "специалист", title: "Специалист", person: "Анна Смирнова", what: "Очередь, карточка обращения, ответ в том же чате", email: "anna@helpflow.demo", Icon: Headset },
  { role: "руководитель", title: "Руководитель поддержки", person: "Администратор", what: "Метрики, команда и база знаний", email: "admin@helpflow.demo", Icon: ChartColumn },
];
const DEMO_PASSWORD = "DemoPass123";

/** The five request types from the case: one click signs in as an employee and sends it. */
const CASE_SCENARIOS = [
  { title: "Простое", text: "Забыл пароль от учётки, не срочно" },
  { title: "Неоднозначное", text: "Ничего не работает, помогите пожалуйста" },
  { title: "Несколько симптомов", text: "Outlook не синхронизируется, а ещё в Zoom нет звука и интернет постоянно отваливается" },
  { title: "Нерешаемое самостоятельно", text: "Нужен доступ к папке бухгалтерии на общем диске" },
  { title: "Срочное", text: "Через 5 минут звонок с клиентом, не запускается Teams, горит!" },
];
function serverMessage(error: ApiError): string | null {
  const detail = error.detail as { message?: unknown } | null | undefined;
  return detail && typeof detail.message === "string" ? detail.message : null;
}

// Shown in `npm run dev` or when a demo build opts in with VITE_SHOW_DEMO_LOGINS=true. Never on by
// default: a production page must not advertise working credentials.
const SHOW_DEMO = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_LOGINS === "true";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const signIn = async (address: string, secret: string, demo = false) => {
    setBusy(true); setMessage("");
    try { await login({ email: address, password: secret, remember_me: remember }); setMessage("Вход выполнен"); }
    catch (error) {
      const locked = error instanceof ApiError && error.status === 429;
      // A lockout is not a typo: keep the password and say how long to wait.
      if (!locked) setPassword("");
      setMessage(!(error instanceof ApiError) ? "Не удалось связаться с сервером"
        : locked || error.status === 403 ? serverMessage(error) ?? "Сейчас войти нельзя, попробуйте позже"
        : demo ? "Демо-аккаунта нет в базе: загрузите демо-данные командой python -m app.seed_demo"
        : "Неверная почта или пароль");
    }
    finally { setBusy(false); }
  };
  return <AuthLayout title="Вход" subtitle="Рабочая почта и пароль. Дальше HelpFlow сам откроет нужный раздел.">
    <form className="auth-form" onSubmit={(event) => {
      event.preventDefault();
      void signIn(email, password);
    }}>
      {message ? <div className="auth-message" role="status">{message}</div> : null}
      <Field label="Email" name="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field label="Пароль" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <label className="auth-check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Запомнить меня</label>
      <button className="auth-submit" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
      <div className="auth-links"><Link to="/forgot-password">Забыли пароль?</Link><Link to="/register">Создать аккаунт</Link></div>
    </form>
    {SHOW_DEMO ? (
      <section className="auth-quick auth-scenarios" aria-labelledby="auth-scenarios-title">
        <h2 id="auth-scenarios-title" className="auth-quick-title">Проверка кейса за две минуты</h2>
        <p className="auth-quick-text">Пять типов обращений из условия кейса. Кнопка входит как сотрудник и отправляет обращение — останется посмотреть, что ответит помощник.</p>
        <ol className="auth-scenario-list">
          {CASE_SCENARIOS.map((scenario, index) => (
            <li key={scenario.title}>
              <button type="button" className="auth-scenario" disabled={busy}
                onClick={() => { rememberScenario(scenario.text); void signIn(DEMO_ACCOUNTS[0].email, DEMO_PASSWORD, true); }}>
                <span className="auth-scenario-number num" aria-hidden="true">{index + 1}</span>
                <span className="auth-quick-body">
                  <span className="auth-quick-name">{scenario.title}</span>
                  <span className="auth-quick-what">«{scenario.text}»</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      </section>
    ) : null}
    {SHOW_DEMO ? (
      <section className="auth-quick" aria-labelledby="auth-quick-title">
        <h2 id="auth-quick-title" className="auth-quick-title">Быстрый вход</h2>
        <p className="auth-quick-text">Демо-аккаунты: посмотрите HelpFlow глазами каждой роли.</p>
        <ul className="auth-quick-list">
          {DEMO_ACCOUNTS.map(({ Icon, ...account }) => (
            <li key={account.email}>
              <button type="button" className="auth-quick-role" disabled={busy}
                aria-label={`Войти как ${account.role}: ${account.person}`}
                onClick={() => { setEmail(account.email); setPassword(DEMO_PASSWORD); void signIn(account.email, DEMO_PASSWORD, true); }}>
                <span className="auth-quick-icon" aria-hidden="true"><Icon size={18} /></span>
                <span className="auth-quick-body">
                  <span className="auth-quick-name">{account.title}</span>
                  <span className="auth-quick-what">{account.what}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    ) : null}
  </AuthLayout>;
}
