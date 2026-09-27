import { useMemo, useState } from "react";
import { Spinner, ErrorState, EmptyState } from "../../components/primitives";
import { useOperatorTickets } from "./useOperatorTickets";
import { TicketFilters } from "./TicketFilters";
import type { TicketFiltersState } from "./TicketFilters";
import { TicketList } from "./TicketList";
import { TicketDetail } from "./TicketDetail";
import { IncidentsSection } from "./IncidentsSection";
import "./OperatorPage.css";

export function OperatorPage() {
  const { phase, tickets, incidents, error, reload } = useOperatorTickets();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filters, setFilters] = useState<TicketFiltersState>({
    search: "",
    urgency: "all",
    service: "all",
  });

  const services = useMemo(
    () => Array.from(new Set(tickets.map((t) => t.service).filter((s): s is string => !!s))),
    [tickets],
  );

  const filtered = useMemo(() => {
    return tickets.filter((ticket) => {
      if (filters.urgency !== "all" && ticket.urgency !== filters.urgency) return false;
      if (filters.service !== "all" && ticket.service !== filters.service) return false;
      if (filters.search.trim()) {
        const haystack = `${ticket.original_request} ${ticket.summary ?? ""}`.toLowerCase();
        if (!haystack.includes(filters.search.trim().toLowerCase())) return false;
      }
      return true;
    });
  }, [tickets, filters]);

  const selected = filtered.find((t) => t.id === selectedId) ?? null;

  if (phase === "loading") {
    return (
      <div className="operator-page operator-page-center">
        <Spinner label="Загружаем очередь…" />
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="operator-page operator-page-center">
        <ErrorState title="Не удалось загрузить очередь" description={error ?? undefined} onRetry={reload} />
      </div>
    );
  }

  return (
    <div className="operator-page">
      <header className="operator-heading">
        <div>
          <h1>Очередь поддержки</h1>
          <p>Обращения, которые HelpFlow передал специалистам</p>
        </div>
        <div className="operator-heading-count" aria-label={`${filtered.length} обращений в очереди`}>
          <strong>{filtered.length}</strong>
          <span>в очереди</span>
        </div>
      </header>
      <IncidentsSection incidents={incidents} />
      <div className="operator-layout">
        <div className={`operator-list-pane${selected ? " operator-list-pane-hide-mobile" : ""}`}>
          <TicketFilters state={filters} services={services} onChange={setFilters} />
          {filtered.length === 0 ? (
            <EmptyState
              title="Нет обращений"
              description="Эскалированные обращения появятся здесь."
            />
          ) : (
            <TicketList tickets={filtered} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </div>
        <div className={`operator-detail-pane${selected ? "" : " operator-detail-pane-hide-mobile"}`}>
          {selected ? (
            <button type="button" className="operator-back-link" onClick={() => setSelectedId(null)}>
              ← К списку
            </button>
          ) : null}
          <TicketDetail ticket={selected} />
        </div>
      </div>
    </div>
  );
}
