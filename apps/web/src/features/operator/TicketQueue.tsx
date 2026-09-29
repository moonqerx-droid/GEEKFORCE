import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import type { OperatorTicket, TicketScope, Urgency } from "../../api/types";
import { EmptyState, ErrorState, Spinner } from "../../components/primitives";
import { URGENCY_SHORT, formatAgo } from "../../lib/labels";
import { slaOf } from "./operatorApi";
import { SORT_LABEL, type QueueSort } from "./queueView";
import { slaView } from "./sla";
import type { QueueView } from "./useQueueView";

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

const FILTERS: { value: Urgency; label: string }[] = [
  { value: "critical", label: "Критичные" },
  { value: "high", label: "Срочные" },
  { value: "normal", label: "Обычные" },
  { value: "low", label: "Не срочные" },
];

export function TicketQueue({
  scope,
  onScopeChange,
  status,
  total,
  view,
  selectedId,
  onSelect,
  currentUserId,
  onRetry,
  top,
}: {
  scope: TicketScope;
  onScopeChange: (scope: TicketScope) => void;
  status: "loading" | "ready" | "error";
  /** Tickets in the tab before search and filters. */
  total: number;
  view: QueueView;
  selectedId: string | null;
  onSelect: (id: string) => void;
  currentUserId: string;
  onRetry: () => void;
  /** Shown above the tabs: the mass-problem radar. */
  top?: ReactNode;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  // The chosen ticket stays in sight, also when it was chosen with «Следующее» or the arrows.
  useEffect(() => {
    if (!selectedId) return;
    listRef.current?.querySelector<HTMLElement>(`[data-ticket="${selectedId}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [selectedId]);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const order = view.order;
    if (!order.length) return;
    event.preventDefault();
    const at = order.findIndex((ticket) => ticket.id === selectedId);
    const next = event.key === "ArrowDown"
      ? order[Math.min(order.length - 1, at + 1)]
      : order[Math.max(0, at < 0 ? 0 : at - 1)];
    onSelect(next.id);
    listRef.current?.querySelector<HTMLElement>(`[data-ticket="${next.id}"]`)?.focus();
  };

  const filtered = view.query.trim() || view.urgency !== "all";

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
            {scope === tab.scope && status === "ready" ? <span className="queue-count num">{total}</span> : null}
          </button>
        ))}
      </div>

      {status === "ready" && total ? (
        <div className="queue-controls">
          <label className="visually-hidden" htmlFor="queue-search">Поиск по обращениям</label>
          <input
            id="queue-search"
            className="queue-search"
            type="search"
            placeholder="Поиск: текст, сотрудник, сервис"
            value={view.query}
            onChange={(event) => view.setQuery(event.target.value)}
          />
          <div className="queue-filters" role="group" aria-label="Срочность">
            <button type="button" className="queue-filter" aria-pressed={view.urgency === "all"}
              onClick={() => view.setUrgency("all")}>Все</button>
            {FILTERS.filter((filter) => view.counts[filter.value]).map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`queue-filter queue-filter-${filter.value}`}
                aria-pressed={view.urgency === filter.value}
                onClick={() => view.setUrgency(view.urgency === filter.value ? "all" : filter.value)}
              >
                {filter.label} <span className="num">{view.counts[filter.value]}</span>
              </button>
            ))}
          </div>
          {scope !== "resolved" ? (
            <label className="queue-sort">
              <span>Порядок</span>
              <select value={view.sort} onChange={(event) => view.setSort(event.target.value as QueueSort)}>
                {(Object.keys(SORT_LABEL) as QueueSort[]).map((key) => (
                  <option key={key} value={key}>{SORT_LABEL[key]}</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}

      {status === "loading" ? <div className="queue-state"><Spinner label="Загружаем очередь…" /></div> : null}
      {status === "error" ? <ErrorState title="Не удалось загрузить очередь" description="Проверьте соединение с сервером." onRetry={onRetry} /> : null}
      {status === "ready" && !total ? <EmptyState title={EMPTY[scope][0]} description={EMPTY[scope][1]} /> : null}
      {status === "ready" && total && !view.shown && filtered ? (
        <EmptyState title="Ничего не нашлось" description="Измените поиск или уберите фильтр срочности." />
      ) : null}

      {status === "ready" && view.shown ? (
        <div className="queue-scroll" ref={listRef} onKeyDown={onKeyDown}>
          {view.sections.map((section) => {
            const folded = Boolean(section.collapsible && !view.expanded.has(section.key));
            return (
              <section key={section.key} className="queue-section" aria-label={section.title ?? "Обращения"}>
                {section.title ? (
                  section.collapsible ? (
                    <button type="button" className="queue-section-title queue-section-toggle"
                      aria-expanded={!folded} onClick={() => view.toggle(section.key)}>
                      <span>{section.title}</span>
                      <span className="queue-section-count num">{section.tickets.length}</span>
                      <span aria-hidden="true">{folded ? "▸" : "▾"}</span>
                    </button>
                  ) : (
                    <h2 className="queue-section-title">
                      <span>{section.title}</span>
                      <span className="queue-section-count num">{section.tickets.length}</span>
                    </h2>
                  )
                ) : null}
                {folded ? null : (
                  <ul className="queue-list">
                    {section.tickets.map((ticket) => (
                      <li key={ticket.id}>
                        <QueueItem ticket={ticket} selected={ticket.id === selectedId}
                          mine={ticket.assignee_id === currentUserId} onSelect={onSelect} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
          <p className="queue-hint">↑ ↓ — переход между обращениями</p>
        </div>
      ) : null}
    </section>
  );
}

function QueueItem({ ticket, selected, mine, onSelect }: {
  ticket: OperatorTicket; selected: boolean; mine: boolean; onSelect: (id: string) => void;
}) {
  // Only a ticket still waiting for its first reply has a clock to watch.
  const sla = slaOf(ticket);
  const clock = sla && !sla.replied_at ? slaView(sla) : null;
  return (
    <button
      type="button"
      data-ticket={ticket.id}
      className={`queue-item queue-item-${ticket.urgency} ${selected ? "queue-item-active" : ""}`}
      onClick={() => onSelect(ticket.id)}
      aria-current={selected}
    >
      <span className="queue-item-top">
        <span className={`queue-urgency queue-urgency-${ticket.urgency}`}>{URGENCY_SHORT[ticket.urgency]}</span>
        <span className="queue-time">{formatAgo(ticket.escalated_at ?? ticket.created_at)}</span>
      </span>
      <span className="queue-summary" title={ticket.summary || ticket.original_request}>{ticket.summary || ticket.original_request}</span>
      <span className="queue-bottom">
        <span className="queue-meta">
          {ticket.owner_name ?? "Сотрудник"}
          {ticket.service ? `, ${ticket.service}` : ""}
        </span>
        <span className="queue-badges">
          {clock ? <span className={`queue-sla sla-${clock.tone}`}>{clock.text}</span> : null}
          {ticket.incident_id ? <span className="queue-incident">Общий сбой</span> : null}
          {ticket.status === "IN_PROGRESS" && !mine ? (
            <span className="queue-owner">В работе: {ticket.assignee_name ?? "специалист"}</span>
          ) : null}
        </span>
      </span>
    </button>
  );
}
