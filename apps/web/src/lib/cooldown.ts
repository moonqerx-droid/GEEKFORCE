import { useEffect, useState } from "react";

/** «Отправить ещё раз» waits as long as the server does; a reload keeps the countdown. */
const PREFIX = "helpflow.cooldown.";

export function startCooldown(key: string, seconds: number) {
  try { window.sessionStorage.setItem(PREFIX + key, String(Date.now() + seconds * 1000)); } catch { /* countdown only */ }
}

function secondsLeft(key: string): number {
  try {
    const until = Number(window.sessionStorage.getItem(PREFIX + key));
    return until ? Math.max(0, Math.ceil((until - Date.now()) / 1000)) : 0;
  } catch {
    return 0;
  }
}

/** Seconds until another email may be requested for `key` (an action plus an address); 0 when it may. */
export function useCooldown(key: string): number {
  const [left, setLeft] = useState(() => secondsLeft(key));
  useEffect(() => {
    setLeft(secondsLeft(key));
    const timer = window.setInterval(() => setLeft(secondsLeft(key)), 1000);
    return () => window.clearInterval(timer);
  }, [key]);
  return left;
}
