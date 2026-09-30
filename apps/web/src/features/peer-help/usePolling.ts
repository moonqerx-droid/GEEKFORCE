import { useEffect, useRef } from "react";

export const PEER_POLL_MS = 4000;

/** Runs `load` now and then every few seconds while the tab is visible. */
export function usePolling(load: () => void, enabled = true, intervalMs = PEER_POLL_MS) {
  const latest = useRef(load);
  useEffect(() => {
    latest.current = load;
  }, [load]);
  useEffect(() => {
    if (!enabled) return;
    latest.current();
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") latest.current();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, intervalMs]);
}
