import { useRef, useState } from "react";
import type { OperatorTicket } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState, Spinner } from "../../components/primitives";
import { MessageThread } from "../conversation/MessageThread";
import { Composer } from "../conversation/Composer";
import { stepMarkers } from "../conversation/steps";
import { formatDateTime } from "../../lib/labels";
import { fillTemplate, slaOf } from "./operatorApi";
import { formatDuration, slaView } from "./sla";
import { TemplatePicker } from "./TemplatePicker";

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
  position,
  onPrevious,
  onNext,
}: {
  onShowCard: () => void;
  /** Where this ticket is in the queue as shown: «3 из 45». */
  position?: { index: number; total: number } | null;
  onPrevious?: () => void;
  onNext?: () => void;
  ticket: OperatorTicket | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  currentUserId: string;
  onAssign: () => Promise<unknown>;
  onReply: (content: string, files: File[]) => Promise<unknown>;
  onResolve: (summary: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState("");
  const threadRef = useRef<HTMLElement>(null);
  const [resolving, setResolving] = useState(false);
  const [summary, setSummary] = useState("");

  if (!ticket) {
    return (
      <section className="workspace workspace-empty">
        {loading ? <Spinner label="Открываем обращение…" /> : (
          <EmptyState
            title="Выберите обращение"
            description="Слева — очередь: новые сверху, порядок можно сменить. Поиск и фильтр по срочности — над списком, стрелки ↑ ↓ переключают обращения. У каждого обращения уже есть карточка от помощника."
          />
        )}
      </section>
    );
  }

  const sla = slaOf(ticket);
  const slaText = slaView(sla);
  const takenByOther = Boolean(ticket.assignee_id && ticket.assignee_id !== currentUserId);
  const open = ticket.status === "ESCALATED" || ticket.status === "IN_PROGRESS";
  const canWrite = open && !takenByOther;

  return (
    <section className="workspace" aria-label="Переписка по обращению" ref={threadRef}>
      {position ? (
        <nav className="workspace-nav" aria-label="Переход по очереди">
          <button type="button" className="workspace-nav-button" disabled={!onPrevious} onClick={onPrevious}>← Предыдущее</button>
          <span className="workspace-nav-position num">{position.index} из {position.total}</span>
          <button type="button" className="workspace-nav-button" disabled={!onNext} onClick={onNext}>Следующее →</button>
        </nav>
      ) : null}
      <header className="workspace-head">
        <div>
          <h1 className="workspace-title" title={ticket.summary || ticket.original_request}>{ticket.summary || ticket.original_request}</h1>
          <p className="workspace-sub">
            {ticket.owner_name ?? "Сотрудник"}, обращение от {formatDateTime(ticket.created_at)}
          </p>
          {sla && slaText ? (
            <p className={`workspace-sla sla-${slaText.tone}`}>
              Первый ответ: норма {formatDuration(sla.target_minutes)}. {slaText.text}
            </p>
          ) : null}
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
        <>
        <TemplatePicker onPick={(template) => {
          const text = fillTemplate(template.body, ticket.owner_name);
          setDraft((current) => (current.trim() ? `${current.trimEnd()}\n\n${text}` : text));
          window.requestAnimationFrame(() => threadRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus());
        }} />
        <Composer
          busy={busy}
          value={draft}
          onValueChange={setDraft}
          tone="human"
          label="Ответ сотруднику"
          placeholder="Ответить сотруднику…"
          allowFiles
          dropTarget={threadRef}
          hint="Можно приложить скриншот с подсказкой, куда нажать: перетащите файл или вставьте через ⌘V / Ctrl+V."
          onSend={async (content, files) => { await onReply(content, files); }}
        />
        </>
      ) : null}
    </section>
  );
}
