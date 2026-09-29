import { useMemo, useState } from "react";
import type { OperatorTicket, TicketScope } from "../../api/types";
import {
  arrangeQueue, searched, urgencyCounts, walkOrder,
  type QueueSort, type UrgencyFilter,
} from "./queueView";

const SORT_KEY = "helpflow.queue.sort";

function savedSort(): QueueSort {
  try {
    const value = window.localStorage.getItem(SORT_KEY);
    return value === "urgent" || value === "waiting" || value === "newest" ? value : "newest";
  } catch {
    return "newest";
  }
}

/** Search, urgency filter and sort for the specialist's queue, plus the order to walk it in. */
export function useQueueView(tickets: OperatorTicket[], scope: TicketScope, currentUserId: string) {
  const [sort, setSortState] = useState<QueueSort>(savedSort);
  const [urgency, setUrgency] = useState<UrgencyFilter>("all");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const sections = useMemo(
    () => arrangeQueue(tickets, { scope, sort, urgency, query, currentUserId }),
    [tickets, scope, sort, urgency, query, currentUserId],
  );
  const order = useMemo(() => walkOrder(sections, expanded), [sections, expanded]);
  const counts = useMemo(() => urgencyCounts(searched(tickets, query)), [tickets, query]);

  const setSort = (next: QueueSort) => {
    setSortState(next);
    try { window.localStorage.setItem(SORT_KEY, next); } catch { /* a convenience only */ }
  };
  const toggle = (key: string) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  return {
    sections, order, counts,
    shown: sections.reduce((sum, section) => sum + section.tickets.length, 0),
    sort, setSort, urgency, setUrgency, query, setQuery, expanded, toggle,
  };
}

export type QueueView = ReturnType<typeof useQueueView>;
