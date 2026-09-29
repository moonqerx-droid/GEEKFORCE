import type { ReactNode } from "react";
import type { OperatorTicket, TicketScope } from "../../api/types";
import { EmptyState, ErrorState, Spinner } from "../../components/primitives";
import { URGENCY_SHORT, formatAgo } from "../../lib/labels";
import { slaOf } from "./operatorApi";
import { slaView } from "./sla";

const TABS: { scope: TicketScope; label: string }[] = [
  { scope: "queue", label: "Открытые" },
  { scope: "mine", label: "Мои" },
  { scope: "resolved", label: "Закрытые" },
];

const EMPTY: Record<TicketScope, [string, string]> = {
  queue: ["Очередь пуста", "Помощник справляется сам. Новые обращения появятся здесь автоматически."],
  mine: ["У вас нет обращений в работе", "Возьмите обращение из вкладки «Открытые»."],
  resolved: ["Пока ничего не закрыто", "Здесь будут обращения, которые решили специалисты."],
};

export function TicketQueue({
  scope,
  onScopeChange,
  tickets,
  status,
  selectedId,
  onSelect,
  currentUserId,
  onRetry,
  top,
}: {
  scope: TicketScope;
  onScopeChange: (scope: TicketScope) => void;
  tickets: OperatorTicket[];
  status: "loading" | "ready" | "error";
  selectedId: string | null;
  onSelect: (id: string) => void;
  currentUserId: string;
  onRetry: () => void;
  /** Shown above the tabs: the mass-problem radar. */
  top?: ReactNode;
}) {
  return (
    <section className="queue" aria-label="Очередь обращений">
      {top}
      <div className="queue-tabs" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.scope}
            type="button"
            role="tab"
            aria-selected={scope === tab.scope}
            className="queue-tab"
            onClick={() => onScopeChange(tab.scope)}
          >
            {tab.label}
            {scope === tab.scope && status === "ready" ? <span className="queue-count num">{tickets.length}</span> : null}
          </button>
        ))}
      </div>

      {status === "loading" ? <div className="queue-state"><Spinner label="Загружаем очередь…" /></div> : null}
      {status === "error" ? <ErrorState title="Не удалось загрузить очередь" description="Проверьте соединение с сервером." onRetry={onRetry} /> : null}
      {status === "ready" && !tickets.length ? <EmptyState title={EMPTY[scope][0]} description={EMPTY[scope][1]} /> : null}

      {status === "ready" && tickets.length ? (
        <ul className="queue-list">
          {tickets.map((ticket) => {
            const mine = ticket.assignee_id === currentUserId;
            // Only a ticket still waiting for its first reply has a clock to watch.
            const sla = slaOf(ticket);
            const clock = sla && !sla.replied_at ? slaView(sla) : null;
            return (
              <li key={ticket.id}>
                <button
                  type="button"
                  className={`queue-item queue-item-${ticket.urgency} ${ticket.id === selectedId ? "queue-item-active" : ""}`}
                  onClick={() => onSelect(ticket.id)}
                  aria-current={ticket.id === selectedId}
                >
                  <span className="queue-item-top">
                    <span className={`queue-urgency queue-urgency-${ticket.urgency}`}>{URGENCY_SHORT[ticket.urgency]}</span>
                    <span className="queue-time">{formatAgo(ticket.escalated_at ?? ticket.created_at)}</span>
                  </span>
                  <span className="queue-summary">{ticket.summary || ticket.original_request}</span>
                  <span className="queue-meta">
                    {ticket.owner_name ?? "Сотрудник"}
                    {ticket.service ? `, ${ticket.service}` : ""}
                  </span>
                  {clock ? <span className={`queue-sla sla-${clock.tone}`}>{clock.text}</span> : null}
                  {ticket.incident_id ? <span className="queue-incident">Общий сбой</span> : null}
                  {ticket.status === "IN_PROGRESS" ? (
                    <span className={`queue-owner ${mine ? "queue-owner-mine" : ""}`}>
                      {mine ? "У вас в работе" : `В работе: ${ticket.assignee_name ?? "специалист"}`}
                    </span>
                  ) : ticket.status === "ESCALATED" ? (
                    <span className="queue-owner queue-owner-free">Ждёт ответа</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
