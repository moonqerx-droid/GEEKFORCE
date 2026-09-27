import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { TicketScope } from "../../api/types";
import { CasePassport } from "../../components/CasePassport";
import { Spinner } from "../../components/primitives";
import { useAuth } from "../auth/AuthProvider";
import { useIncidents } from "../incidents/incidents";
import { IncidentRadar } from "./IncidentRadar";
import { IncidentWorkspace } from "./IncidentWorkspace";
import { TicketQueue } from "./TicketQueue";
import { TicketWorkspace } from "./TicketWorkspace";
import { useTicket, useTicketQueue } from "./useTickets";
import "./OperatorPage.css";

const FALLBACK_LABEL: Record<string, string> = {
  low_confidence: "модель не была уверена",
  llm_error: "модель не ответила",
  unknown_source: "модель сослалась на неутверждённый источник",
};

export function OperatorPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [scope, setScope] = useState<TicketScope>("queue");
  const selectedId = params.get("ticket");
  const incidentId = params.get("incident");
  const radar = useIncidents();
  const queue = useTicketQueue(scope);
  const reloadQueue = queue.reload;
  const onChanged = useCallback(() => { void reloadQueue(); }, [reloadQueue]);
  const current = useTicket(selectedId, onChanged);
  const currentUserId = user?.id ?? "";

  const select = (id: string) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.delete("incident");
    next.set("ticket", id);
    return next;
  });
  const selectIncident = (id: string) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.delete("ticket");
    next.set("incident", id);
    return next;
  });
  const incident = incidentId ? radar.incidents?.find((item) => item.id === incidentId) ?? null : null;

  const ticket = current.ticket;

  return (
    <div className="operator">
      <TicketQueue
        scope={scope}
        onScopeChange={setScope}
        tickets={queue.tickets}
        status={queue.status}
        selectedId={selectedId}
        onSelect={select}
        currentUserId={currentUserId}
        onRetry={() => void queue.reload()}
        top={radar.incidents ? (
          <IncidentRadar incidents={radar.incidents} selectedId={incidentId} onSelect={selectIncident} />
        ) : null}
      />
      {incidentId && radar.incidents ? (
        <IncidentWorkspace
          key={incidentId}
          incident={incident}
          onChanged={(changed) => {
            radar.replace(changed);
            onChanged();
          }}
          onOpenTicket={select}
        />
      ) : incidentId ? (
        <section className="workspace workspace-empty"><Spinner label="Открываем сбой…" /></section>
      ) : <TicketWorkspace
        key={selectedId ?? "none"}
        ticket={ticket}
        loading={Boolean(selectedId)}
        busy={current.busy}
        error={current.error}
        currentUserId={currentUserId}
        onAssign={current.assign}
        onReply={current.reply}
        onResolve={current.resolve}
      />}
      <div className="operator-side">
        {incidentId ? (
          <aside className="radar-explain">
            <h2>Как радар находит сбой</h2>
            <p>
              Когда за два часа к специалистам попадают три похожих обращения про один сервис, радар
              объединяет их. Следующие такие обращения присоединяются сразу: сотрудник видит, что это общий
              сбой, и не тратит время на диагностику.
            </p>
            <p>Одно сообщение отсюда придёт в чат каждому затронутому. Когда сбой устранён, закройте его: обращения закроются вместе с ним.</p>
          </aside>
        ) : ticket ? (
          <>
            <CasePassport conversation={ticket} audience="operator" />
            {ticket.rag_source_ids.length || ticket.ai_fallback_reason ? (
              <details className="operator-provenance">
                <summary>Откуда помощник брал ответы</summary>
                {ticket.rag_source_ids.length ? (
                  <>
                    <p>Источники ответа из базы знаний:</p>
                    <ul>{ticket.rag_source_ids.map((source) => <li key={source}><code>{source}</code></li>)}</ul>
                  </>
                ) : null}
                {ticket.ai_fallback_reason ? (
                  <p>
                    Использован безопасный ответ по правилам
                    {FALLBACK_LABEL[ticket.ai_fallback_reason] ? `: ${FALLBACK_LABEL[ticket.ai_fallback_reason]}` : ""}.
                  </p>
                ) : null}
              </details>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
