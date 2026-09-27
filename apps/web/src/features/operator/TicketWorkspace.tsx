import { useState } from "react";
import type { OperatorTicket } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState, Spinner } from "../../components/primitives";
import { MessageThread } from "../conversation/MessageThread";
import { Composer } from "../conversation/Composer";
import { stepMarkers } from "../conversation/steps";
import { formatDateTime } from "../../lib/labels";

export function TicketWorkspace({
  ticket,
  loading,
  busy,
  error,
  currentUserId,
  onAssign,
  onReply,
  onResolve,
  onShowCard,
}: {
  onShowCard: () => void;
  ticket: OperatorTicket | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  currentUserId: string;
  onAssign: () => Promise<unknown>;
  onReply: (content: string) => Promise<unknown>;
  onResolve: (summary: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState("");
  const [resolving, setResolving] = useState(false);
  const [summary, setSummary] = useState("");

  if (!ticket) {
    return (
      <section className="workspace workspace-empty">
        {loading ? <Spinner label="Открываем обращение…" /> : (
          <EmptyState
            title="Выберите обращение"
            description="Слева — очередь, срочные наверху. У каждого обращения уже есть карточка от помощника: что случилось, что спрашивали и что пробовали."
          />
        )}
      </section>
    );
  }

  const takenByOther = Boolean(ticket.assignee_id && ticket.assignee_id !== currentUserId);
  const open = ticket.status === "ESCALATED" || ticket.status === "IN_PROGRESS";
  const canWrite = open && !takenByOther;

  return (
    <section className="workspace" aria-label="Переписка по обращению">
      <header className="workspace-head">
        <div>
          <h1 className="workspace-title">{ticket.summary || ticket.original_request}</h1>
          <p className="workspace-sub">
            {ticket.owner_name ?? "Сотрудник"}, обращение от {formatDateTime(ticket.created_at)}
          </p>
        </div>
        <div className="workspace-actions">
        <Button variant="ghost" className="workspace-card-toggle" onClick={onShowCard}>Карточка</Button>
        {ticket.status === "ESCALATED" && !ticket.assignee_id ? (
          <Button variant="human" busy={busy} title="Первый ответ тоже закрепит обращение за вами" onClick={() => void onAssign().catch(() => undefined)}>Взять в работу</Button>
        ) : null}
        {ticket.status === "IN_PROGRESS" && !takenByOther && !resolving ? (
          <Button variant="secondary" disabled={busy} onClick={() => setResolving(true)}>Закрыть обращение</Button>
        ) : null}
        </div>
      </header>

      {error ? <div className="workspace-alert" role="alert">{error}</div> : null}
      {takenByOther && open ? (
        <div className="workspace-note" role="status">Обращение ведёт {ticket.assignee_name}. Вы можете читать переписку.</div>
      ) : null}

      <div className="workspace-thread">
        <MessageThread messages={ticket.messages} viewer="operator" employeeName={ticket.owner_name} steps={stepMarkers(ticket)} />
        {ticket.status === "RESOLVED" ? (
          <div className="workspace-note workspace-note-done">
            Закрыто {ticket.resolved_at ? formatDateTime(ticket.resolved_at) : ""}
            {ticket.rating ? `. Оценка сотрудника: ${ticket.rating} из 5` : ""}
            {ticket.rating_comment ? ` — «${ticket.rating_comment}»` : ""}
          </div>
        ) : null}
      </div>

      {resolving ? (
        <form
          className="workspace-resolve"
          onSubmit={(event) => {
            event.preventDefault();
            if (!summary.trim()) return;
            void onResolve(summary.trim()).then(() => {
              setResolving(false);
              setSummary("");
            }).catch(() => undefined);
          }}
        >
          <label htmlFor="resolve-summary" className="workspace-resolve-label">Что сделали? Сотрудник увидит этот итог.</label>
          <textarea
            id="resolve-summary"
            className="workspace-resolve-input"
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder="Например: сбросила зависшую сессию CRM, вход восстановлен"
            rows={2}
            maxLength={2000}
            autoFocus
          />
          <div className="workspace-resolve-actions">
            <Button type="button" variant="ghost" onClick={() => setResolving(false)}>Отмена</Button>
            <Button type="submit" variant="human" busy={busy} disabled={!summary.trim()}>Закрыть и сообщить сотруднику</Button>
          </div>
        </form>
      ) : canWrite ? (
        <Composer
          busy={busy}
          value={draft}
          onValueChange={setDraft}
          tone="human"
          label="Ответ сотруднику"
          placeholder="Ответить сотруднику…"
          onSend={async (content) => { await onReply(content); }}
        />
      ) : null}
    </section>
  );
}
