import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import { ConflictError, ValidationError } from "../../api/errors";
import type { InviteResult, TeamMember } from "../../api/types";
import { Button } from "../../components/Button";
import { Avatar, Badge, ErrorState, Spinner } from "../../components/primitives";
import { useAuth } from "../auth/AuthProvider";
import { formatAgo } from "../../lib/labels";
import "./Admin.css";

const STATUS: Record<TeamMember["status"], { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Работает", tone: "success" },
  invited: { label: "Приглашён", tone: "warning" },
  disabled: { label: "Отключён", tone: "neutral" },
};

export function AdminTeam() {
  const { user } = useAuth();
  const [team, setTeam] = useState<TeamMember[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [invite, setInvite] = useState<InviteResult | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    api.listTeam().then((data) => { setTeam(data); setFailed(false); }).catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    setCopied(false);
    try {
      setInvite(await api.inviteOperator(form));
      setForm({ first_name: "", last_name: "", email: "" });
      load();
    } catch (error) {
      setFormError(error instanceof ConflictError ? "Человек с такой почтой уже есть в системе."
        : error instanceof ValidationError ? "Проверьте имя, фамилию и почту." : "Не получилось отправить приглашение.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (member: TeamMember) => {
    const updated = await api.setMemberActive(member.id, member.status !== "active").catch(() => null);
    if (updated) setTeam((current) => current?.map((item) => (item.id === updated.id ? updated : item)) ?? null);
  };

  const copy = async () => {
    if (!invite) return;
    try {
      await navigator.clipboard.writeText(invite.invite_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="admin admin-team">
      <header className="admin-head">
        <h1 className="admin-title">Команда поддержки</h1>
        <p className="admin-sub">Специалисты отвечают сотрудникам, когда помощник не справился. Добавить человека можно только по приглашению.</p>
      </header>

      <section className="admin-block invite">
        <h2>Пригласить специалиста</h2>
        <form className="invite-form" onSubmit={submit}>
          <label>
            <span>Имя</span>
            <input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} autoComplete="off" />
          </label>
          <label>
            <span>Фамилия</span>
            <input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} autoComplete="off" />
          </label>
          <label className="invite-email">
            <span>Рабочая почта</span>
            <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="off" />
          </label>
          <Button type="submit" variant="human" busy={busy}>Пригласить</Button>
        </form>
        {formError ? <p className="invite-error" role="alert">{formError}</p> : null}
        {invite ? (
          <div className="invite-result" role="status">
            <p>
              {invite.email_sent ? "Письмо с приглашением отправлено. " : "Почта не настроена, поэтому передайте ссылку сами. "}
              Ссылка действует 7 дней.
            </p>
            <div className="invite-link">
              <input readOnly value={invite.invite_url} aria-label="Ссылка-приглашение" onFocus={(e) => e.target.select()} />
              <Button variant="secondary" onClick={() => void copy()}>{copied ? "Скопировано" : "Скопировать"}</Button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="admin-block">
        <h2>Состав</h2>
        {failed ? <ErrorState title="Не удалось загрузить команду" onRetry={load} /> : null}
        {!team && !failed ? <Spinner label="Загружаем команду…" /> : null}
        {team ? (
          <ul className="members">
            {team.map((member) => (
              <li key={member.id} className="member">
                <Avatar kind="human" name={member.name} size={36} />
                <div className="member-main">
                  <span className="member-name">{member.name}{member.role === "admin" ? <span className="member-role"> руководитель</span> : null}</span>
                  <span className="member-email">{member.email}</span>
                </div>
                <span className="member-seen">
                  {member.status === "invited" ? `приглашён ${formatAgo(member.created_at)}`
                    : member.last_login_at ? `был ${formatAgo(member.last_login_at)}` : "ещё не входил"}
                </span>
                <Badge tone={STATUS[member.status].tone}>{STATUS[member.status].label}</Badge>
                {member.status !== "invited" && member.id !== user?.id ? (
                  <Button variant="ghost" onClick={() => void toggle(member)}>
                    {member.status === "active" ? "Отключить" : "Включить"}
                  </Button>
                ) : <span className="member-spacer" />}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
