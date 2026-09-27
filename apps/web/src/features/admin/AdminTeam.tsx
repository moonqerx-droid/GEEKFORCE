import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError, ConflictError } from "../../api/client";
import type { AdminUser, Department, TemporaryCredential, UserRole } from "../../api/types";
import { Button } from "../../components/Button";
import { TemporaryPasswordDialog } from "../../components/TemporaryPasswordDialog";
import { Avatar, ErrorState, Spinner } from "../../components/primitives";
import { DEPARTMENT_LABEL, DEPARTMENTS, ROLE_SHORT, formatAgo } from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { UserPanel } from "./UserPanel";
import "./AdminTeam.css";

type RoleFilter = "all" | UserRole;
type StatusFilter = "all" | "active" | "disabled" | "temporary";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function AdminTeam() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<RoleFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  // The one-time password lives only here and is dropped the moment the dialog closes.
  const [credential, setCredential] = useState<{ value: TemporaryCredential; reason: "created" | "reset" } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.listUsers(controller.signal)
      .then((data) => { setUsers(data); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [attempt]);

  const upsert = useCallback((next: AdminUser) => {
    setUsers((current) => {
      if (!current) return [next];
      return current.some((item) => item.id === next.id)
        ? current.map((item) => (item.id === next.id ? next : item))
        : [...current, next];
    });
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (users ?? []).filter((item) => (
      (!needle || item.name.toLowerCase().includes(needle) || item.email.toLowerCase().includes(needle))
      && (role === "all" || item.role === role)
      && (status === "all"
        || (status === "temporary" ? item.must_change_password : item.status === status))
    ));
  }, [users, query, role, status]);

  const open = users?.find((item) => item.id === openId) ?? null;
  const filtered = query || role !== "all" || status !== "all";

  return (
    <div className="team">
      <header className="team-head">
        <div>
          <h1 className="team-title">Пользователи</h1>
          <p className="team-sub">
            Все, у кого есть доступ к HelpFlow. Сотрудники регистрируются сами, специалистов поддержки создаёте вы.
          </p>
        </div>
        {users ? (
          <dl className="team-counts">
            <div><dt>Всего</dt><dd className="num">{users.length}</dd></div>
            <div><dt>Специалистов</dt><dd className="num">{users.filter((item) => item.role === "operator").length}</dd></div>
            <div><dt>Ждут смены пароля</dt><dd className="num">{users.filter((item) => item.must_change_password).length}</dd></div>
          </dl>
        ) : null}
      </header>

      <CreateSpecialist onCreated={(value) => { upsert(value.user); setCredential({ value, reason: "created" }); }} />

      <section className="team-directory" aria-labelledby="directory-title">
        <h2 id="directory-title" className="visually-hidden">Каталог пользователей</h2>
        <div className="team-filters">
          <label className="team-search" htmlFor="team-search">
            <span className="visually-hidden">Поиск по имени или почте</span>
            <input id="team-search" type="search" className="field-input" placeholder="Имя или почта"
              value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Поиск по имени или почте" />
          </label>
          <label className="team-filter" htmlFor="team-role">
            <span>Роль</span>
            <select id="team-role" className="field-input" value={role} onChange={(event) => setRole(event.target.value as RoleFilter)}>
              <option value="all">Все роли</option>
              <option value="employee">Сотрудники</option>
              <option value="operator">Специалисты</option>
              <option value="admin">Руководители</option>
            </select>
          </label>
          <label className="team-filter" htmlFor="team-status">
            <span>Статус</span>
            <select id="team-status" className="field-input" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
              <option value="all">Все</option>
              <option value="active">Активные</option>
              <option value="disabled">Отключённые</option>
              <option value="temporary">С временным паролем</option>
            </select>
          </label>
        </div>

        {!users && !failed ? <div className="team-state"><Spinner label="Загружаем пользователей…" /></div> : null}
        {failed && !users ? (
          <ErrorState title="Не удалось загрузить пользователей" description="Проверьте соединение с сервером."
            onRetry={() => { setFailed(false); setAttempt((n) => n + 1); }} />
        ) : null}

        {users ? (
          <>
            <table className="team-table" aria-label="Пользователи">
              <thead>
                <tr>
                  <th scope="col">Человек</th>
                  <th scope="col">Роль</th>
                  <th scope="col">Подразделение</th>
                  <th scope="col">Статус</th>
                  <th scope="col">Последний вход</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id} className={item.id === openId ? "team-row-open" : ""}>
                    <td data-label="Человек">
                      <button type="button" className="team-person" onClick={() => setOpenId(item.id)}>
                        <Avatar kind={item.role === "employee" ? "employee" : "human"} name={item.name} size={34} />
                        <span className="team-person-text">
                          <span className="team-person-name">{item.name}{item.id === me?.id ? <span className="team-you"> это вы</span> : null}</span>
                          <span className="team-person-email">{item.email}</span>
                        </span>
                      </button>
                    </td>
                    <td data-label="Роль"><span className={`team-role team-role-${item.role}`}>{ROLE_SHORT[item.role]}</span></td>
                    <td data-label="Подразделение">{DEPARTMENT_LABEL[item.department]}</td>
                    <td data-label="Статус">
                      <span className={`team-status team-status-${item.status}`}>{item.status === "active" ? "Активен" : "Отключён"}</span>
                      {item.must_change_password ? <span className="team-flag">Ждёт смены пароля</span> : null}
                    </td>
                    <td data-label="Последний вход" className="team-seen">
                      {item.last_login_at ? formatAgo(item.last_login_at) : "ещё не входил"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visible.length ? (
              <div className="team-empty">
                <p className="team-empty-title">{filtered ? "Никого не нашли" : "Пока никого нет"}</p>
                {filtered ? (
                  <Button variant="ghost" onClick={() => { setQuery(""); setRole("all"); setStatus("all"); }}>Сбросить фильтры</Button>
                ) : <p>Создайте первого специалиста поддержки выше.</p>}
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      {open ? (
        <UserPanel
          key={open.id}
          user={open}
          isSelf={open.id === me?.id}
          onClose={() => setOpenId(null)}
          onUpdated={upsert}
          onCredential={(value, reason) => { upsert(value.user); setCredential({ value, reason }); }}
        />
      ) : null}

      {credential ? (
        <TemporaryPasswordDialog
          name={credential.value.user.name}
          email={credential.value.user.email}
          password={credential.value.temporary_password}
          reason={credential.reason}
          onDone={() => setCredential(null)}
        />
      ) : null}
    </div>
  );
}

function CreateSpecialist({ onCreated }: { onCreated: (credential: TemporaryCredential) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [department, setDepartment] = useState<Department | "">("");
  const [errors, setErrors] = useState<{ name?: string; email?: string; department?: string }>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const fullName = name.trim().replace(/\s+/g, " ");
    const mail = email.trim().toLowerCase();
    const next: typeof errors = {};
    if (fullName.split(" ").length < 2 || fullName.length < 3) next.name = "Укажите имя и фамилию";
    if (!mail) next.email = "Укажите рабочую почту";
    else if (!EMAIL.test(mail)) next.email = "Проверьте почту";
    if (!department) next.department = "Выберите подразделение";
    setErrors(next);
    setProblem("");
    if (Object.keys(next).length || !department) return;
    setBusy(true);
    try {
      const credential = await api.createOperator({ full_name: fullName, email: mail, department });
      setName("");
      setEmail("");
      setDepartment("");
      onCreated(credential);
    } catch (error) {
      setProblem(error instanceof ConflictError ? "Человек с такой почтой уже есть в системе."
        : error instanceof ApiError && error.status === 422 ? "Имя и фамилия — только буквы, пробел или дефис; проверьте почту."
          : "Не удалось создать специалиста. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  };

  const describe = (key: keyof typeof errors) => (errors[key] ? `create-${key}-error` : undefined);

  return (
    <section className="team-create" aria-labelledby="create-title">
      <div className="team-create-intro">
        <h2 id="create-title">Новый специалист поддержки</h2>
        <p>Мы создадим аккаунт и покажем временный пароль. При первом входе специалист задаст свой.</p>
      </div>
      <form className="team-create-form" onSubmit={submit} noValidate aria-labelledby="create-title">
        <div className="pw-field">
          <label htmlFor="create-name">Имя и фамилия</label>
          <input id="create-name" className="field-input" value={name} maxLength={101} autoComplete="off"
            aria-invalid={Boolean(errors.name)} aria-describedby={describe("name")}
            onChange={(event) => setName(event.target.value)} />
          {errors.name ? <small id="create-name-error" className="pw-error">{errors.name}</small> : null}
        </div>
        <div className="pw-field">
          <label htmlFor="create-email">Рабочая почта</label>
          <input id="create-email" className="field-input" type="email" value={email} maxLength={254} autoComplete="off"
            aria-invalid={Boolean(errors.email)} aria-describedby={describe("email")}
            onChange={(event) => setEmail(event.target.value)} />
          {errors.email ? <small id="create-email-error" className="pw-error">{errors.email}</small> : null}
        </div>
        <div className="pw-field">
          <label htmlFor="create-department">Подразделение</label>
          <select id="create-department" className="field-input" value={department}
            aria-invalid={Boolean(errors.department)} aria-describedby={describe("department")}
            onChange={(event) => setDepartment(event.target.value as Department)}>
            <option value="">Выберите</option>
            {DEPARTMENTS.map((item) => <option key={item} value={item}>{DEPARTMENT_LABEL[item]}</option>)}
          </select>
          {errors.department ? <small id="create-department-error" className="pw-error">{errors.department}</small> : null}
        </div>
        <Button type="submit" variant="blue" busy={busy}>Создать специалиста</Button>
      </form>
      {problem ? <p className="pw-failure team-create-problem" role="alert">{problem}</p> : null}
    </section>
  );
}
