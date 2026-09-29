import type { OperatorTicket, TicketScope, Urgency } from "../../api/types";

/** How the specialist reads the queue. Newest first by default: a fresh request must never hide at the bottom. */
export type QueueSort = "newest" | "urgent" | "waiting";
export type UrgencyFilter = "all" | Urgency;

export const SORT_LABEL: Record<QueueSort, string> = {
  newest: "Сначала новые",
  urgent: "Сначала срочные",
  waiting: "Дольше всех ждут",
};

export interface QueueSection {
  key: "waiting" | "mine" | "colleagues" | "all";
  title: string | null;
  tickets: OperatorTicket[];
  /** Colleagues' work is visible but not the specialist's task: folded until asked for. */
  collapsible?: boolean;
}

export interface QueueOptions {
  scope: TicketScope;
  sort: QueueSort;
  urgency: UrgencyFilter;
  query: string;
  currentUserId: string;
}

const URGENCY_RANK: Record<Urgency, number> = { critical: 0, high: 1, normal: 2, low: 3 };

function handedOverAt(ticket: OperatorTicket): number {
  return new Date(ticket.escalated_at ?? ticket.created_at).getTime();
}

function compare(sort: QueueSort) {
  return (a: OperatorTicket, b: OperatorTicket) => {
    if (sort === "waiting") return handedOverAt(a) - handedOverAt(b);
    if (sort === "urgent") {
      const byUrgency = URGENCY_RANK[a.urgency] - URGENCY_RANK[b.urgency];
      if (byUrgency) return byUrgency;
    }
    return handedOverAt(b) - handedOverAt(a);
  };
}

function matches(ticket: OperatorTicket, query: string): boolean {
  const needle = query.trim().toLowerCase().replaceAll("ё", "е");
  if (!needle) return true;
  const haystack = [ticket.summary, ticket.original_request, ticket.owner_name, ticket.service, ticket.assignee_name]
    .filter(Boolean).join(" ").toLowerCase().replaceAll("ё", "е");
  return haystack.includes(needle);
}

/** Tickets after search, before the urgency filter: the filter buttons count these. */
export function searched(tickets: OperatorTicket[], query: string): OperatorTicket[] {
  return tickets.filter((ticket) => matches(ticket, query));
}

export function urgencyCounts(tickets: OperatorTicket[]): Record<Urgency, number> {
  const counts: Record<Urgency, number> = { critical: 0, high: 0, normal: 0, low: 0 };
  for (const ticket of tickets) counts[ticket.urgency] += 1;
  return counts;
}

export function arrangeQueue(tickets: OperatorTicket[], options: QueueOptions): QueueSection[] {
  const shown = searched(tickets, options.query)
    .filter((ticket) => options.urgency === "all" || ticket.urgency === options.urgency);
  if (options.scope === "resolved") {
    // Closed ones read as a history: the latest closed first, as the server sends them.
    return [{ key: "all", title: null, tickets: shown }];
  }
  const sorted = [...shown].sort(compare(options.sort));
  if (options.scope === "mine") return [{ key: "all", title: null, tickets: sorted }];
  const sections: QueueSection[] = [
    { key: "waiting", title: "Ждут ответа", tickets: sorted.filter((t) => t.status === "ESCALATED") },
    { key: "mine", title: "У вас в работе",
      tickets: sorted.filter((t) => t.status === "IN_PROGRESS" && t.assignee_id === options.currentUserId) },
    { key: "colleagues", title: "В работе у коллег", collapsible: true,
      tickets: sorted.filter((t) => t.status === "IN_PROGRESS" && t.assignee_id !== options.currentUserId) },
  ];
  return sections.filter((section) => section.tickets.length);
}

/** The order the specialist walks through with ↑/↓ and «Следующее»: folded sections are skipped. */
export function walkOrder(sections: QueueSection[], expanded: ReadonlySet<string>): OperatorTicket[] {
  return sections.flatMap((section) => (section.collapsible && !expanded.has(section.key) ? [] : section.tickets));
}
