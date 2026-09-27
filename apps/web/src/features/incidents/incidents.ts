import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Incident, IncidentStatus } from "../../api/types";
import { plural } from "../../lib/labels";
import "./Incidents.css";

export const INCIDENT_POLL_MS = 5000;

export const INCIDENT_STATUS_LABEL: Record<IncidentStatus, string> = {
  CANDIDATE: "Похоже на сбой",
  ACTIVE: "Подтверждён",
  RESOLVED: "Устранён",
};

export function serviceName(incident: Incident): string {
  return incident.service_label || incident.service.toUpperCase();
}

export function affectedCount(incident: Incident): number {
  return incident.affected_employees || incident.conversation_count;
}

/** "VPN не работает у 4 сотрудников" */
export function incidentHeadline(incident: Incident): string {
  const count = affectedCount(incident);
  return `${serviceName(incident)} не работает у ${count} ${plural(count, "сотрудника", "сотрудников", "сотрудников")}`;
}

export function sinceTime(incident: Incident): string {
  return incident.first_seen_at ?? incident.created_at;
}

/**
 * Open incidents, refreshed in the background. `null` means the list is not available
 * (still loading or the server refused): the radar then simply stays hidden.
 */
export function useIncidents(pollMs = INCIDENT_POLL_MS) {
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => api.listIncidents(controller.signal)
      .then(setIncidents)
      .catch(() => {
        if (!controller.signal.aborted) setIncidents((current) => current ?? null);
      });
    void load();
    const timer = window.setInterval(() => void load(), pollMs);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [pollMs, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  // Show an action's result at once, without waiting for the next poll.
  const replace = useCallback((incident: Incident) => {
    setIncidents((current) => (current ?? [])
      .map((item) => (item.id === incident.id ? incident : item))
      .filter((item) => item.status !== "RESOLVED"));
  }, []);

  return { incidents, reload, replace };
}
