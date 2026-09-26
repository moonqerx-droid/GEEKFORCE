import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { NotFoundError } from "../../api/errors";
import type { Incident, OperatorTicket } from "../../api/types";

const POLL_INTERVAL_MS = 15000;

type Phase = "loading" | "ready" | "error";

export function useOperatorTickets() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [tickets, setTickets] = useState<OperatorTicket[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await api.listTickets();
      setTickets(data);
      setError(null);
      setPhase("ready");
    } catch {
      setError("Не удалось загрузить очередь обращений.");
      setPhase("error");
    } finally {
      inFlight.current = false;
    }

    try {
      const data = await api.listIncidents();
      setIncidents(Array.isArray(data) ? data : []);
    } catch (err) {
      // Incident Radar endpoint may not exist yet — hide the section silently.
      if (!(err instanceof NotFoundError)) {
        setIncidents([]);
      } else {
        setIncidents([]);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void load();
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  return { phase, tickets, incidents, error, reload: load };
}
