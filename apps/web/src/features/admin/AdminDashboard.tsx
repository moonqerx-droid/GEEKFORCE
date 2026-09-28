import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Metrics, Urgency } from "../../api/types";
import { ErrorState, Spinner } from "../../components/primitives";
import { URGENCY_SHORT, formatMinutes, plural } from "../../lib/labels";
import { ActiveIncidents } from "./ActiveIncidents";
import { AdminTemplates } from "./AdminTemplates";
import { SlaFact } from "./SlaFact";
import { DailyChart } from "./DailyChart";
import "./Admin.css";

const PERIODS = [7, 30] as const;
const URGENCY_ORDER: Urgency[] = ["critical", "high", "normal", "low"];

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function AdminDashboard() {
  const [days, setDays] = useState<(typeof PERIODS)[number]>(7);
  const [attempt, setAttempt] = useState(0);
  // Each answer remembers which request it belongs to; a stale one reads as "loading".
  const [result, setResult] = useState<{ key: string; metrics: Metrics | null } | null>(null);
  const key = `${days}:${attempt}`;

  useEffect(() => {
    const controller = new AbortController();
    const requestKey = `${days}:${attempt}`;
    api.metrics(days, controller.signal)
      .then((data) => setResult({ key: requestKey, metrics: data }))
      .catch(() => {
        if (!controller.signal.aborted) setResult({ key: requestKey, metrics: null });
      });
    return () => controller.abort();
  }, [days, attempt]);

  const failed = result?.key === key && result.metrics === null;
  const metrics = result?.metrics ?? null;

  if (failed) {
    return <div className="admin"><ErrorState title="Не удалось загрузить метрики" description="Проверьте соединение с сервером." onRetry={() => setAttempt((n) => n + 1)} /></div>;
  }
  if (!metrics) {
    return <div className="admin admin-center"><Spinner label="Считаем метрики…" /></div>;
  }

  const resolved = metrics.resolved_by_assistant + metrics.resolved_by_operator;
  const maxProblem = Math.max(1, ...metrics.top_problems.map((item) => item.count));
  const urgencyTotal = Math.max(1, URGENCY_ORDER.reduce((sum, level) => sum + metrics.urgency[level], 0));

  return (
    <div className="admin">
      <header className="admin-head">
        <div className="admin-period" role="group" aria-label="Период">
          {PERIODS.map((period) => (
            <button key={period} type="button" aria-pressed={days === period} onClick={() => setDays(period)}>
              {period} дней
            </button>
          ))}
        </div>
        <p className="admin-kicker">
          За {days} дней {metrics.total} {plural(metrics.total, "обращение", "обращения", "обращений")}
        </p>
        <h1 className="admin-headline">
          Помощник сам решил <span className="admin-big num">{percent(metrics.self_service_rate)}</span>
        </h1>
        <p className="admin-sub">
          {metrics.resolved_by_assistant} из {resolved} закрытых обращений — без участия специалиста.
          Остальные {metrics.resolved_by_operator} решила команда, получив готовую карточку.
        </p>
      </header>

      <section className="admin-facts" aria-label="Скорость и качество">
        <div className="admin-fact">
          <span className="admin-fact-value">{formatMinutes(metrics.median_resolution_minutes)}</span>
          <span className="admin-fact-label">медианное время до решения</span>
        </div>
        <div className="admin-fact">
          <span className="admin-fact-value">{formatMinutes(metrics.median_first_reply_minutes)}</span>
          <span className="admin-fact-label">до первого ответа специалиста</span>
        </div>
        <SlaFact days={days} />
        <div className="admin-fact">
          <span className="admin-fact-value">{metrics.average_rating ? metrics.average_rating.toFixed(1).replace(".", ",") : "—"}</span>
          <span className="admin-fact-label">средняя оценка, {metrics.ratings_count} {plural(metrics.ratings_count, "оценка", "оценки", "оценок")}</span>
        </div>
        <Link to="/operator" className={`admin-fact admin-fact-link ${metrics.waiting ? "admin-fact-alert" : ""}`}>
          <span className="admin-fact-value">{metrics.waiting}</span>
          <span className="admin-fact-label">ждут специалиста прямо сейчас</span>
        </Link>
      </section>

      <ActiveIncidents />

      <section className="admin-block admin-block-wide">
        <h2>Обращения по дням</h2>
        <DailyChart days={metrics.daily} />
      </section>

      <section className="admin-block">
        <h2>С чем обращаются</h2>
        <p className="admin-note">Доля эскалаций показывает, где помощнику нужны новые сценарии.</p>
        {metrics.top_problems.length ? (
          <ul className="problems">
            {metrics.top_problems.map((item) => (
              <li key={item.playbook_id} className="problem">
                <span className="problem-name">{item.service ?? item.playbook_id}</span>
                <span className="problem-bar" aria-hidden="true">
                  <i style={{ width: `${(item.count / maxProblem) * 100}%` }} />
                </span>
                <span className="problem-count num">{item.count}</span>
                <span className={`problem-esc num ${item.escalation_rate >= 0.5 ? "problem-esc-high" : ""}`}>
                  {percent(item.escalation_rate)} к специалисту
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="admin-note">Пока нет обращений за период.</p>}
      </section>

      <section className="admin-block">
        <h2>Срочность</h2>
        <div className="urgency-bar" role="img" aria-label={URGENCY_ORDER.map((level) => `${URGENCY_SHORT[level]}: ${metrics.urgency[level]}`).join(", ")}>
          {URGENCY_ORDER.map((level) => metrics.urgency[level] ? (
            <i key={level} className={`urgency-seg urgency-seg-${level}`} style={{ flexGrow: metrics.urgency[level] / urgencyTotal }} />
          ) : null)}
        </div>
        <ul className="urgency-legend">
          {URGENCY_ORDER.map((level) => (
            <li key={level}>
              <i className={`urgency-seg-${level}`} />
              {URGENCY_SHORT[level]} <b className="num">{metrics.urgency[level]}</b>
            </li>
          ))}
        </ul>

        <h2 className="admin-block-sub">Команда</h2>
        {metrics.operators.length ? (
          <table className="load">
            <thead>
              <tr><th>Специалист</th><th>В работе</th><th>Закрыто</th><th>Медиана</th><th>Оценка</th></tr>
            </thead>
            <tbody>
              {metrics.operators.map((operator) => (
                <tr key={operator.id} className={operator.is_active ? "" : "load-off"}>
                  <td>{operator.name}</td>
                  <td className="num">{operator.in_progress}</td>
                  <td className="num">{operator.resolved}</td>
                  <td className="num">{formatMinutes(operator.median_resolution_minutes)}</td>
                  <td className="num">{operator.average_rating ? operator.average_rating.toFixed(1).replace(".", ",") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="admin-note">В команде пока нет специалистов. <Link to="/admin/team">Создать специалиста</Link></p>}
      </section>
      <AdminTemplates />
    </div>
  );
}
