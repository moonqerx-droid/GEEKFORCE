import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import type { Department, PersonalMetrics, Profile } from "../../api/types";
import { Button } from "../../components/Button";
import { PeriodSwitch } from "../../components/PeriodSwitch";
import type { Period } from "../../lib/period";
import { Avatar, ErrorState, Spinner } from "../../components/primitives";
import {
  DEPARTMENT_LABEL,
  DEPARTMENTS,
  ROLE_LABEL,
  formatDateLong,
  formatMinutes,
  formatRating,
} from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { ChangePasswordForm } from "./ChangePasswordForm";
import "./ProfilePage.css";

function plural(count: number, one: string, few: string, many: string) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function ProfilePage() {
  const { refresh } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api.profile(controller.signal)
      .then((data) => { setProfile(data); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [attempt]);

  if (failed && !profile) {
    return (
      <div className="profile profile-center">
        <ErrorState title="Не удалось загрузить профиль" description="Проверьте соединение с сервером." onRetry={() => setAttempt((n) => n + 1)} />
      </div>
    );
  }
  if (!profile) {
    return <div className="profile profile-center"><Spinner label="Загружаем профиль…" /></div>;
  }

  return (
    <div className="profile">
      <header className="profile-head">
        <Avatar kind={profile.role === "employee" ? "employee" : "human"} name={profile.name} size={72} />
        <div className="profile-id">
          <h1 className="profile-name">{profile.name}</h1>
          <p className="profile-role">
            <span>{ROLE_LABEL[profile.role]}</span>
            <span className="profile-dept">{DEPARTMENT_LABEL[profile.department]}</span>
          </p>
        </div>
        <dl className="profile-facts">
          <div>
            <dt>Статус</dt>
            <dd><span className={`profile-status ${profile.is_active ? "" : "profile-status-off"}`}>{profile.is_active ? "Активен" : "Отключён"}</span></dd>
          </div>
          <div>
            <dt>Последний вход</dt>
            <dd>{formatDateLong(profile.last_login_at)}</dd>
          </div>
          <div>
            <dt>В HelpFlow с</dt>
            <dd>{new Date(profile.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}</dd>
          </div>
        </dl>
      </header>

      <div className="profile-body">
        {profile.role === "operator" ? <MyMetrics /> : null}

        <section className="profile-section" aria-labelledby="account-title">
          <div className="profile-section-head">
            <h2 id="account-title">Данные аккаунта</h2>
            <p>Почту меняет руководитель поддержки: она же логин для входа.</p>
          </div>
          <AccountForm
            profile={profile}
            onSaved={async (next) => { setProfile(next); await refresh(); }}
          />
        </section>

        <section className="profile-section" aria-labelledby="security-title">
          <div className="profile-section-head">
            <h2 id="security-title">Безопасность</h2>
            <p>После смены пароля все другие сеансы завершатся, этот останется открытым.</p>
          </div>
          <ChangePasswordForm name="Смена пароля" />
        </section>
      </div>
    </div>
  );
}

function AccountForm({ profile, onSaved }: { profile: Profile; onSaved: (profile: Profile) => Promise<void> }) {
  const [name, setName] = useState(profile.name);
  const [department, setDepartment] = useState<Department>(profile.department);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const changed = name.trim() !== profile.name || department !== profile.department;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim().replace(/\s+/g, " ");
    if (trimmed.length < 2) {
      setMessage({ tone: "error", text: "Укажите имя и фамилию" });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const payload = {
        ...(trimmed !== profile.name ? { full_name: trimmed } : {}),
        ...(department !== profile.department ? { department } : {}),
      };
      const next = await api.updateProfile(payload);
      setName(next.name);
      setDepartment(next.department);
      await onSaved(next);
      setMessage({ tone: "ok", text: "Сохранено" });
    } catch (error) {
      setMessage({
        tone: "error",
        text: error instanceof ApiError && error.status === 422
          ? "Имя и фамилия: только буквы, пробел, дефис или апостроф."
          : "Не удалось сохранить. Попробуйте ещё раз.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="profile-form" aria-label="Данные аккаунта" onSubmit={submit} noValidate>
      <label className="pw-field" htmlFor="profile-name">
        <span>Имя и фамилия</span>
        <input id="profile-name" className="field-input" value={name} maxLength={101} autoComplete="name"
          onChange={(event) => setName(event.target.value)} />
      </label>
      <div className="pw-field">
        <span>Почта</span>
        <p className="profile-readonly">{profile.email}</p>
      </div>
      <label className="pw-field" htmlFor="profile-department">
        <span>Подразделение</span>
        <select id="profile-department" className="field-input" value={department}
          onChange={(event) => setDepartment(event.target.value as Department)}>
          {DEPARTMENTS.map((item) => <option key={item} value={item}>{DEPARTMENT_LABEL[item]}</option>)}
        </select>
      </label>
      {message ? (
        <p className={message.tone === "ok" ? "pw-done" : "pw-failure"} role={message.tone === "ok" ? "status" : "alert"}>{message.text}</p>
      ) : null}
      <div>
        <Button type="submit" variant="blue" busy={busy} disabled={!changed}>Сохранить</Button>
      </div>
    </form>
  );
}

function MyMetrics() {
  const [days, setDays] = useState<Period>(30);
  const [result, setResult] = useState<{ days: Period; data: PersonalMetrics | null } | null>(null);
  const [attempt, setAttempt] = useState(0);

  const load = useCallback((signal: AbortSignal) => {
    const requested = days;
    api.profileMetrics(requested, signal)
      .then((data) => setResult({ days: requested, data }))
      .catch(() => { if (!signal.aborted) setResult({ days: requested, data: null }); });
  }, [days]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, attempt]);

  const current = result?.days === days ? result : null;
  const metrics = current?.data ?? null;
  const empty = metrics && !metrics.resolved && !metrics.in_progress && !metrics.waiting_first_reply;

  return (
    <section className="profile-section profile-metrics" aria-labelledby="metrics-title">
      <div className="profile-section-head profile-section-head-row">
        <div>
          <h2 id="metrics-title">Мои показатели</h2>
          <p>Только ваша работа, без сравнения с коллегами.</p>
        </div>
        <PeriodSwitch value={days} onChange={setDays} />
      </div>
      {!current ? <Spinner label="Считаем показатели…" /> : null}
      {current && !metrics ? (
        <ErrorState title="Не удалось посчитать показатели" onRetry={() => setAttempt((n) => n + 1)} />
      ) : null}
      {empty ? <p className="profile-empty">За этот период обращений не было</p> : null}
      {metrics && !empty ? (
        <dl className="kpis">
          <div className="kpi kpi-lead"><dt>Закрыто</dt><dd className="num">{metrics.resolved}</dd></div>
          <div className="kpi"><dt>В работе</dt><dd className="num">{metrics.in_progress}</dd></div>
          <div className={`kpi ${metrics.waiting_first_reply ? "kpi-alert" : ""}`}><dt>Ждут первого ответа</dt><dd className="num">{metrics.waiting_first_reply}</dd></div>
          <div className="kpi"><dt>Первый ответ, медиана</dt><dd>{formatMinutes(metrics.median_first_reply_minutes)}</dd></div>
          <div className="kpi"><dt>Решение, медиана</dt><dd>{formatMinutes(metrics.median_resolution_minutes)}</dd></div>
          <div className="kpi">
            <dt>Оценка</dt>
            <dd>{formatRating(metrics.average_rating)}</dd>
            <span className="kpi-note">{metrics.ratings_count} {plural(metrics.ratings_count, "оценка", "оценки", "оценок")}</span>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
