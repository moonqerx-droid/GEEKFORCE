import { useState, type FormEvent } from "react";
import { api, ApiError, ConflictError } from "../../api/client";
import type { AdminUser, AdminUserUpdate, Department, TemporaryCredential, UserRole } from "../../api/types";
import { Button } from "../../components/Button";
import { Dialog } from "../../components/Dialog";
import { DEPARTMENT_LABEL, DEPARTMENTS, ROLE_SHORT, formatDateLong } from "../../lib/labels";
import { SpecialistMetricsView } from "./SpecialistMetricsView";

interface Draft {
  full_name: string;
  email: string;
  department: Department;
  role: UserRole;
  is_active: boolean;
}

function draftOf(user: AdminUser): Draft {
  return { full_name: user.name, email: user.email, department: user.department, role: user.role, is_active: user.is_active };
}

/** Only fields the admin actually changed against `base`: a save must never revert someone else's edit. */
function changesOf(draft: Draft, base: AdminUser): Omit<AdminUserUpdate, "revision"> {
  const baseDraft = draftOf(base);
  const changes: Omit<AdminUserUpdate, "revision"> = {};
  const name = draft.full_name.trim().replace(/\s+/g, " ");
  if (name !== baseDraft.full_name) changes.full_name = name;
  const email = draft.email.trim().toLowerCase();
  if (email !== baseDraft.email) changes.email = email;
  if (draft.department !== baseDraft.department) changes.department = draft.department;
  if (draft.role !== baseDraft.role) changes.role = draft.role;
  if (draft.is_active !== baseDraft.is_active) changes.is_active = draft.is_active;
  return changes;
}

function detailText(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail as unknown;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  }
  return "";
}

export function UserPanel({
  user,
  isSelf,
  onClose,
  onUpdated,
  onCredential,
}: {
  user: AdminUser;
  isSelf: boolean;
  onClose: () => void;
  onUpdated: (user: AdminUser) => void;
  onCredential: (credential: TemporaryCredential, reason: "reset") => void;
}) {
  const hasMetrics = user.role !== "employee";
  const [tab, setTab] = useState<"metrics" | "account">(hasMetrics ? "metrics" : "account");

  return (
    <Dialog title={user.name} placement="side" onDismiss={onClose}>
      <div className="upanel-sub">
        <span>{user.email}</span>
        <span>{ROLE_SHORT[user.role]}</span>
        <span>{DEPARTMENT_LABEL[user.department]}</span>
      </div>
      <button type="button" className="upanel-close" onClick={onClose} aria-label="Закрыть панель">×</button>

      <div className="upanel-tabs" role="tablist" aria-label="Разделы пользователя">
        {hasMetrics ? (
          <button type="button" role="tab" id="tab-metrics" aria-controls="panel-metrics"
            aria-selected={tab === "metrics"} onClick={() => setTab("metrics")}>Показатели</button>
        ) : null}
        <button type="button" role="tab" id="tab-account" aria-controls="panel-account"
          aria-selected={tab === "account"} onClick={() => setTab("account")}>Аккаунт</button>
      </div>

      {tab === "metrics" && hasMetrics ? (
        <div role="tabpanel" id="panel-metrics" aria-labelledby="tab-metrics">
          <SpecialistMetricsView userId={user.id} />
        </div>
      ) : (
        <div role="tabpanel" id="panel-account" aria-labelledby="tab-account" className="upanel-account">
          <AccountEditor user={user} isSelf={isSelf} onUpdated={onUpdated} />
          <ResetPassword user={user} onCredential={onCredential} />
          <dl className="upanel-meta">
            <div><dt>Создан</dt><dd>{formatDateLong(user.created_at)}</dd></div>
            <div><dt>Последний вход</dt><dd>{user.last_login_at ? formatDateLong(user.last_login_at) : "ещё не входил"}</dd></div>
          </dl>
        </div>
      )}
    </Dialog>
  );
}

function AccountEditor({ user, isSelf, onUpdated }: {
  user: AdminUser; isSelf: boolean; onUpdated: (user: AdminUser) => void;
}) {
  // `base` is the version the edits started from; after a conflict it moves only on the admin's choice.
  const [base, setBase] = useState(user);
  const [draft, setDraft] = useState<Draft>(() => draftOf(user));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState("");
  const [conflict, setConflict] = useState<AdminUser | null>(null);
  const changes = changesOf(draft, base);
  const dirty = Object.keys(changes).length > 0;

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setSaved(false);
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const save = async (revision: number, payload: Omit<AdminUserUpdate, "revision">) => {
    setBusy(true);
    setProblem("");
    setSaved(false);
    try {
      const next = await api.updateUser(user.id, { revision, ...payload });
      setBase(next);
      setDraft(draftOf(next));
      setConflict(null);
      setSaved(true);
      onUpdated(next);
    } catch (error) {
      const detail = detailText(error);
      if (error instanceof ConflictError && /email/i.test(detail)) {
        setProblem("Эта почта уже занята другим пользователем.");
      } else if (error instanceof ConflictError) {
        const fresh = await api.listUsers().then((users) => users.find((item) => item.id === user.id) ?? null).catch(() => null);
        setConflict(fresh);
        if (!fresh) setProblem("Данные пользователя изменились, а загрузить новую версию не получилось. Попробуйте ещё раз.");
        if (fresh) onUpdated(fresh);
      } else if (error instanceof ApiError && error.status === 400) {
        setProblem(detail || "Это изменение запрещено.");
      } else if (error instanceof ApiError && error.status === 422) {
        setProblem("Проверьте имя и почту: имя — только буквы, пробел или дефис.");
      } else {
        setProblem("Не удалось сохранить. Попробуйте ещё раз.");
      }
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!dirty || conflict) return;
    if (changes.full_name !== undefined && changes.full_name.length < 2) {
      setProblem("Укажите имя и фамилию.");
      return;
    }
    void save(base.revision, changes);
  };

  return (
    <form className="upanel-form" aria-label="Данные пользователя" onSubmit={submit} noValidate>
      {conflict ? (
        <div className="upanel-conflict" role="alert">
          <p>
            <strong>Пока вы редактировали, данные этого пользователя изменились.</strong> Ваши правки не потеряны,
            они остались в форме. Сейчас в системе: {conflict.name}, {conflict.email}, {ROLE_SHORT[conflict.role]},
            {" "}{DEPARTMENT_LABEL[conflict.department]}, {conflict.is_active ? "активен" : "отключён"}.
          </p>
          <div className="upanel-conflict-actions">
            <Button variant="blue" busy={busy} onClick={() => void save(conflict.revision, changes)}>Сохранить мои изменения поверх</Button>
            <Button variant="secondary" disabled={busy} onClick={() => {
              setBase(conflict);
              setDraft(draftOf(conflict));
              setConflict(null);
            }}>Взять актуальные данные</Button>
          </div>
        </div>
      ) : null}

      <label className="pw-field" htmlFor="u-name">
        <span>Имя и фамилия</span>
        <input id="u-name" className="field-input" value={draft.full_name} maxLength={101}
          onChange={(event) => set("full_name", event.target.value)} />
      </label>
      <label className="pw-field" htmlFor="u-email">
        <span>Почта</span>
        <input id="u-email" className="field-input" type="email" value={draft.email} maxLength={254}
          onChange={(event) => set("email", event.target.value)} />
      </label>
      <div className="upanel-row">
        <label className="pw-field" htmlFor="u-department">
          <span>Подразделение</span>
          <select id="u-department" className="field-input" value={draft.department}
            onChange={(event) => set("department", event.target.value as Department)}>
            {DEPARTMENTS.map((item) => <option key={item} value={item}>{DEPARTMENT_LABEL[item]}</option>)}
          </select>
        </label>
        <label className="pw-field" htmlFor="u-role">
          <span>Роль</span>
          <select id="u-role" className="field-input" value={draft.role} disabled={isSelf}
            aria-describedby={isSelf ? "u-self-note" : undefined}
            onChange={(event) => set("role", event.target.value as UserRole)}>
            {(["employee", "operator", "admin"] as UserRole[]).map((role) => <option key={role} value={role}>{ROLE_SHORT[role]}</option>)}
          </select>
        </label>
      </div>
      <label className="upanel-check">
        <input type="checkbox" checked={draft.is_active} disabled={isSelf}
          onChange={(event) => set("is_active", event.target.checked)} />
        <span>
          Аккаунт активен
          <small>Отключённый пользователь не сможет войти, его текущие сеансы завершатся.</small>
        </span>
      </label>
      {isSelf ? <p id="u-self-note" className="upanel-note">Свою роль и активность поменять нельзя, чтобы не потерять доступ к управлению.</p> : null}
      {changes.email || changes.role || changes.is_active === false ? (
        <p className="upanel-note">После сохранения все сеансы этого пользователя завершатся.</p>
      ) : null}
      {problem ? <p className="pw-failure" role="alert">{problem}</p> : null}
      {saved ? <p className="pw-done" role="status">Изменения сохранены</p> : null}
      <div>
        <Button type="submit" variant="blue" busy={busy && !conflict} disabled={!dirty || Boolean(conflict)}>Сохранить изменения</Button>
      </div>
    </form>
  );
}

function ResetPassword({ user, onCredential }: {
  user: AdminUser; onCredential: (credential: TemporaryCredential, reason: "reset") => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  const reset = async () => {
    setBusy(true);
    setProblem("");
    try {
      const credential = await api.resetUserPassword(user.id);
      setConfirming(false);
      onCredential(credential, "reset");
    } catch {
      setProblem("Не удалось сбросить пароль. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="upanel-reset" aria-labelledby="reset-title">
      <h3 id="reset-title">Пароль</h3>
      <p>
        Текущий пароль узнать нельзя: HelpFlow хранит только его хеш. Если человек забыл пароль,
        выдайте новый временный — при входе он сразу задаст свой.
      </p>
      {user.must_change_password ? <p className="upanel-note">Сейчас у пользователя временный пароль, он ещё не задал свой.</p> : null}
      {problem ? <p className="pw-failure" role="alert">{problem}</p> : null}
      <div>
        <Button variant="secondary" onClick={() => setConfirming(true)}>Сбросить пароль</Button>
      </div>
      {confirming ? (
        <Dialog title={`Сбросить пароль для ${user.name}?`} role="alertdialog" tone="important" onDismiss={() => setConfirming(false)}>
          <p>
            Текущий пароль перестанет работать, все сеансы пользователя завершатся. Новый временный пароль мы покажем
            один раз — передайте его человеку лично или по защищённому каналу.
          </p>
          <div className="dialog-actions">
            <Button variant="secondary" onClick={() => setConfirming(false)} data-autofocus>Отмена</Button>
            <Button variant="important" busy={busy} onClick={() => void reset()}>Сбросить и показать новый</Button>
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
