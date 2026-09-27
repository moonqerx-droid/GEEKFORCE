import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { SpecialistMetrics, Urgency } from "../../api/types";
import { PeriodSwitch } from "../../components/PeriodSwitch";
import type { Period } from "../../lib/period";
import { ErrorState, Spinner } from "../../components/primitives";
import { URGENCY_SHORT, formatMinutes, formatPercent, formatRating } from "../../lib/labels";
import "./SpecialistMetricsView.css";

const URGENCY_ORDER: Urgency[] = ["critical", "high", "normal", "low"];

function plural(count: number, one: string, few: string, many: string) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function dayLabel(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

export function SpecialistMetricsView({ userId }: { userId: string }) {
  const [days, setDays] = useState<Period>(30);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data: SpecialistMetrics | null } | null>(null);
  const key = `${userId}:${days}:${attempt}`;

  const load = useCallback((signal: AbortSignal) => {
    const requestKey = `${userId}:${days}:${attempt}`;
    api.userMetrics(userId, days, signal)
      .then((data) => setResult({ key: requestKey, data }))
      .catch(() => { if (!signal.aborted) setResult({ key: requestKey, data: null }); });
  }, [userId, days, attempt]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const current = result?.key === key ? result : null;
  const m = current?.data ?? null;
  const empty = m && !m.assigned && !m.resolved && !m.in_progress && !m.waiting_first_reply;

  return (
    <div className="smx">
      <div className="smx-bar">
        <p className="smx-caption">Показатели за выбранный период. Целевое время первого ответа задаётся в настройках сервиса.</p>
        <PeriodSwitch value={days} onChange={setDays} />
      </div>

      {!current ? <Spinner label="Считаем показатели…" /> : null}
      {current && !m ? <ErrorState title="Не удалось посчитать показатели" onRetry={() => setAttempt((n) => n + 1)} /> : null}
      {empty ? <p className="smx-empty">За этот период обращений не было</p> : null}

      {m && !empty ? (
        <>
          <dl className="smx-load">
            <div><dt>Назначено</dt><dd className="num">{m.assigned}</dd></div>
            <div><dt>Закрыто</dt><dd className="num smx-strong">{m.resolved}</dd></div>
            <div><dt>В работе</dt><dd className="num">{m.in_progress}</dd></div>
            <div className={m.waiting_first_reply ? "smx-alert" : ""}><dt>Ждут первого ответа</dt><dd className="num">{m.waiting_first_reply}</dd></div>
          </dl>

          <table className="smx-times">
            <caption className="visually-hidden">Время реакции</caption>
            <thead>
              <tr><th scope="col" /><th scope="col">Медиана</th><th scope="col">90% обращений быстрее</th></tr>
            </thead>
            <tbody>
              <tr><th scope="row">Первый ответ</th><td>{formatMinutes(m.median_first_reply_minutes)}</td><td>{formatMinutes(m.p90_first_reply_minutes)}</td></tr>
              <tr><th scope="row">Решение</th><td>{formatMinutes(m.median_resolution_minutes)}</td><td>{formatMinutes(m.p90_resolution_minutes)}</td></tr>
            </tbody>
          </table>

          <dl className="smx-quality">
            <div>
              <dt>Ответ в целевое время</dt>
              <dd>{formatPercent(m.first_reply_sla_rate)}</dd>
              {m.first_reply_sla_rate != null ? (
                <span className="smx-meter" aria-hidden="true"><i style={{ width: `${Math.round(m.first_reply_sla_rate * 100)}%` }} /></span>
              ) : null}
            </div>
            <div>
              <dt>Оценка</dt>
              <dd>{formatRating(m.average_rating)}</dd>
              <span className="smx-note">{m.ratings_count} {plural(m.ratings_count, "оценка", "оценки", "оценок")}</span>
            </div>
          </dl>

          <section className="smx-block" aria-labelledby="smx-daily">
            <h3 id="smx-daily">Закрыто по дням</h3>
            {m.daily.length ? <DailyBars daily={m.daily} /> : <p className="smx-note">Закрытых обращений за период нет.</p>}
          </section>

          <div className="smx-split">
            <section className="smx-block" aria-labelledby="smx-topics">
              <h3 id="smx-topics">Темы</h3>
              {m.topics.length ? <Topics topics={m.topics} /> : <p className="smx-note">Нет данных.</p>}
            </section>
            <section className="smx-block" aria-labelledby="smx-urgency">
              <h3 id="smx-urgency">Срочность</h3>
              <UrgencyMix urgency={m.urgency} />
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}

function DailyBars({ daily }: { daily: { date: string; resolved: number }[] }) {
  const max = Math.max(1, ...daily.map((day) => day.resolved));
  const every = daily.length > 14 ? Math.ceil(daily.length / 7) : 1;
  return (
    <figure className="smx-daily">
      <div className="smx-daily-bars">
        {daily.map((day) => (
          <div key={day.date} className="smx-daily-col" title={`${dayLabel(day.date)}: ${day.resolved}`}>
            <span className="smx-daily-bar" style={{ height: `${Math.max(day.resolved ? 6 : 0, (day.resolved / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="smx-daily-axis" aria-hidden="true">
        {daily.map((day, index) => (
          <span key={day.date}>{index % every === 0 || index === daily.length - 1 ? dayLabel(day.date) : ""}</span>
        ))}
      </div>
      <details className="smx-table">
        <summary>Показать таблицей</summary>
        <table>
          <thead><tr><th scope="col">День</th><th scope="col">Закрыто обращений</th></tr></thead>
          <tbody>{daily.map((day) => <tr key={day.date}><td>{dayLabel(day.date)}</td><td className="num">{day.resolved}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}

function Topics({ topics }: { topics: { name: string; count: number }[] }) {
  const max = Math.max(1, ...topics.map((topic) => topic.count));
  return (
    <ul className="smx-topics">
      {topics.map((topic) => (
        <li key={topic.name}>
          <span className="smx-topic-name">{topic.name}</span>
          <span className="smx-topic-count num">{topic.count}</span>
          <span className="smx-topic-bar" aria-hidden="true"><i style={{ width: `${(topic.count / max) * 100}%` }} /></span>
        </li>
      ))}
    </ul>
  );
}

function UrgencyMix({ urgency }: { urgency: Record<string, number> }) {
  const total = URGENCY_ORDER.reduce((sum, level) => sum + (urgency[level] ?? 0), 0);
  if (!total) return <p className="smx-note">Нет данных.</p>;
  return (
    <>
      <div className="smx-urgency" role="img" aria-label={URGENCY_ORDER.map((level) => `${URGENCY_SHORT[level]}: ${urgency[level] ?? 0}`).join(", ")}>
        {URGENCY_ORDER.map((level) => (urgency[level] ? (
          <i key={level} className={`smx-urg smx-urg-${level}`} style={{ flexGrow: urgency[level] }} />
        ) : null))}
      </div>
      <ul className="smx-urgency-legend">
        {URGENCY_ORDER.map((level) => (
          <li key={level}><i className={`smx-urg-${level}`} />{URGENCY_SHORT[level]} <b className="num">{urgency[level] ?? 0}</b></li>
        ))}
      </ul>
    </>
  );
}
