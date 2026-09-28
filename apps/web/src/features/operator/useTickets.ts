import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { ApiError, ConflictError } from "../../api/errors";
import type { OperatorTicket, TicketScope } from "../../api/types";

export const QUEUE_POLL_MS = 5000;
export const TICKET_POLL_MS = 3000;

/** Queue for one tab, refreshed in the background so new requests appear on their own. */
export function useTicketQueue(scope: TicketScope) {
  // Results remember their tab, so switching tabs reads as "loading" without resetting state in an effect.
  const [result, setResult] = useState<{ scope: TicketScope; tickets: OperatorTicket[]; failed: boolean } | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await api.listTickets(scope, signal);
      setResult({ scope, tickets: data, failed: false });
    } catch {
      if (!signal?.aborted) {
        setResult((current) => (current?.scope === scope && !current.failed ? current : { scope, tickets: [], failed: true }));
      }
    }
  }, [scope]);

  const current = result?.scope === scope ? result : null;
  const tickets = current?.tickets ?? [];
  const status: "loading" | "ready" | "error" = !current ? "loading" : current.failed ? "error" : "ready";

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal), QUEUE_POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load]);

  return { tickets, status, reload: () => load() };
}

/** The open ticket plus the specialist's actions on it. */
export function useTicket(id: string | null, onChanged: () => void) {
  const [loaded, setLoaded] = useState<OperatorTicket | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ id: string | null; message: string } | null>(null);
  const busyRef = useRef(false);
  // Anything loaded for a previously selected ticket is simply not shown.
  const ticket = loaded && loaded.id === id ? loaded : null;
  const error = failure && failure.id === id ? failure.message : null;

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    const load = () => {
      if (busyRef.current) return;
      api.getTicket(id, controller.signal).then(setLoaded).catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, TICKET_POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [id]);

  const run = useCallback(async (action: () => Promise<OperatorTicket>) => {
    busyRef.current = true;
    setBusy(true);
    setFailure(null);
    try {
      setLoaded(await action());
      onChanged();
    } catch (err) {
      const refused = err instanceof ApiError && (err.status === 413 || err.status === 415) && typeof err.detail === "string";
      setFailure({ id, message: err instanceof ConflictError
        ? "Обращение уже взял другой специалист или оно закрыто. Обновили карточку."
        : refused ? `Файл не прикреплён: ${err.detail as string}` : "Не получилось выполнить действие. Попробуйте ещё раз." });
      if (id) api.getTicket(id).then(setLoaded).catch(() => undefined);
      throw err;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [id, onChanged]);

  return {
    ticket,
    busy,
    error,
    assign: () => (id ? run(() => api.assignTicket(id)) : Promise.resolve()),
    reply: (content: string, files: File[] = []) => (id ? run(async () => {
      // Upload first; a refused file stops the reply so nothing half-sent reaches the employee.
      const ids: string[] = [];
      for (const file of files) ids.push((await api.uploadTicketAttachment(id, file)).id);
      return api.replyToTicket(id, content, ids);
    }) : Promise.resolve()),
    resolve: (summary: string) => (id ? run(() => api.resolveTicket(id, summary)) : Promise.resolve()),
  };
}
