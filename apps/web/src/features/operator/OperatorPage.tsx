import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { TicketScope } from "../../api/types";
import { CasePassport } from "../../components/CasePassport";
import { useAuth } from "../auth/AuthProvider";
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
  const queue = useTicketQueue(scope);
  const reloadQueue = queue.reload;
  const onChanged = useCallback(() => { void reloadQueue(); }, [reloadQueue]);
  const current = useTicket(selectedId, onChanged);
  const currentUserId = user?.id ?? "";

  const select = (id: string) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set("ticket", id);
    return next;
  });

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
      />
      <TicketWorkspace
        key={selectedId ?? "none"}
        ticket={ticket}
        loading={Boolean(selectedId)}
        busy={current.busy}
        error={current.error}
        currentUserId={currentUserId}
        onAssign={current.assign}
        onReply={current.reply}
        onResolve={current.resolve}
      />
      <div className="operator-side">
        {ticket ? (
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
