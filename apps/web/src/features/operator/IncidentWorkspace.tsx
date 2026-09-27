import { useState } from "react";
import { api } from "../../api/client";
import { ConflictError } from "../../api/errors";
import type { Incident } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/primitives";
import { DEPARTMENT_LABEL, formatAgo, formatTime, plural } from "../../lib/labels";
import {
  INCIDENT_STATUS_LABEL,
  affectedCount,
  incidentHeadline,
  serviceName,
  sinceTime,
} from "../incidents/incidents";

/** One outage: who is affected, why they were grouped, and one message for everyone. */
export function IncidentWorkspace({
  incident,
  onChanged,
  onOpenTicket,
}: {
  incident: Incident | null;
  onChanged: (incident: Incident) => void;
  onOpenTicket: (id: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [closing, setClosing] = useState(false);
  const [closingText, setClosingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!incident) {
    return (
      <section className="workspace workspace-empty">
        <EmptyState title="Сбой уже закрыт" description="Он пропал из списка массовых проблем. Обращения сотрудников остались в очереди и в истории." />
      </section>
    );
  }

  const name = serviceName(incident);
  const count = affectedCount(incident);
  const members = incident.members ?? [];

  const run = async (action: () => Promise<Incident>, done: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      onChanged(await action());
      setNotice(done || null);
      return true;
    } catch (err) {
      setError(err instanceof ConflictError
        ? "Сбой успели изменить: список обновился, проверьте и повторите."
        : "Не получилось. Попробуйте ещё раз.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    const text = message.trim();
    if (!text) return;
    const sent = await run(async () => {
      const result = await api.broadcastIncident(incident.id, text, incident.revision);
      return result.incident;
    }, `Отправили ${count} ${plural(count, "сотруднику", "сотрудникам", "сотрудникам")}. Сообщение появится у них в чате.`);
    if (sent) setMessage("");
  };

  const startClosing = () => {
    setClosingText(`${name} снова работает. Проверьте, пожалуйста, у себя. Если что-то не так, напишите сюда.`);
    setClosing(true);
  };

  return (
    <section className="workspace incident" aria-label={`Общий сбой: ${name}`}>
      <header className="workspace-head">
        <div>
          <span className={`incident-chip incident-chip-${incident.status.toLowerCase()}`}>
            {INCIDENT_STATUS_LABEL[incident.status]}
          </span>
          <h1 className="workspace-title">{incidentHeadline(incident)}</h1>
          <p className="workspace-sub">
            Первое обращение {formatAgo(sinceTime(incident))}, в {formatTime(sinceTime(incident))}
          </p>
        </div>
        {incident.status === "CANDIDATE" ? (
          <Button variant="human" busy={busy} onClick={() => void run(
            () => api.confirmIncident(incident.id, incident.revision), "",
          )}>
            Подтвердить сбой
          </Button>
        ) : null}
      </header>

      {error ? <div className="workspace-alert" role="alert">{error}</div> : null}
      {notice ? <div className="workspace-note" role="status">{notice}</div> : null}

      <div className="incident-body">
        {incident.status === "ACTIVE" ? (
          <p className="incident-state">
            <strong>Сбой подтверждён</strong>
            <span> Новые похожие обращения попадут сюда сразу, а сотрудники увидят, что вы уже чините.</span>
          </p>
        ) : (
          <p className="incident-state">
            Радар заметил похожие обращения. Подтвердите сбой, если это действительно общая проблема.
          </p>
        )}

        <p className="incident-why">
          Объединили, потому что совпадают сервис и признаки: {incident.evidence_tokens.join(", ")}
        </p>

        <h2 className="incident-subtitle">Обращения ({members.length || incident.conversation_count})</h2>
        <ul className="incident-members">
          {members.map((member) => (
            <li key={member.id}>
              <button type="button" className="incident-member" onClick={() => onOpenTicket(member.id)}>
                <span className="incident-member-top">
                  <span className="incident-member-name">{member.owner_name ?? "Сотрудник"}</span>
                  <span className="incident-member-meta">
                    {member.owner_department ? `${DEPARTMENT_LABEL[member.owner_department]}, ` : ""}
                    {formatAgo(member.created_at)}
                  </span>
                </span>
                <span className="incident-member-words">{member.original_request}</span>
              </button>
            </li>
          ))}
        </ul>

        {incident.latest_update ? (
          <p className="incident-latest">
            Последнее сообщение всем, {formatTime(incident.latest_update.created_at)}: «{incident.latest_update.message}»
          </p>
        ) : null}
      </div>

      {closing ? (
        <form
          className="workspace-resolve"
          onSubmit={(event) => {
            event.preventDefault();
            const text = closingText.trim();
            if (!text) return;
            void run(() => api.resolveIncident(incident.id, text, incident.revision), "Сбой закрыт.");
          }}
        >
          <label htmlFor="incident-close" className="workspace-resolve-label">
            Сбой устранён? Это сообщение получат все, и их обращения закроются.
          </label>
          <textarea
            id="incident-close"
            className="workspace-resolve-input"
            value={closingText}
            onChange={(event) => setClosingText(event.target.value)}
            rows={2}
            maxLength={1000}
          />
          <div className="workspace-resolve-actions">
            <Button type="button" variant="ghost" onClick={() => setClosing(false)}>Отмена</Button>
            <Button type="submit" variant="human" busy={busy} disabled={!closingText.trim()}>
              Закрыть {count} {plural(count, "обращение", "обращения", "обращений")}
            </Button>
          </div>
        </form>
      ) : (
        <form
          className="incident-broadcast"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <label htmlFor="incident-message" className="workspace-resolve-label">Сообщение всем затронутым</label>
          <textarea
            id="incident-message"
            className="workspace-resolve-input"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={`Например: чиним ${name}, ориентир 15 минут. Ничего перезапускать не нужно.`}
            rows={2}
            maxLength={1000}
          />
          <div className="workspace-resolve-actions">
            <Button type="button" variant="ghost" disabled={busy} onClick={startClosing}>Сбой устранён</Button>
            <Button type="submit" variant="human" busy={busy} disabled={!message.trim()}>
              Отправить {count} {plural(count, "сотруднику", "сотрудникам", "сотрудникам")}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
