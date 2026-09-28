import type { Sla } from "./operatorApi";

export type SlaTone = "ok" | "warning" | "breached" | "met" | "missed";

/** "25 мин", "1 ч", "1 ч 25 мин". */
export function formatDuration(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (!hours) return `${rest} мин`;
  return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
}

/**
 * What to show for a first-reply SLA. While a ticket waits, the countdown is recomputed from
 * `due_at` on every render, so the label changes between polls without trusting a stale state.
 */
export function slaView(sla: Sla | null, now = Date.now()): { tone: SlaTone; text: string } | null {
  if (!sla) return null;
  if (sla.replied_at) {
    return sla.state === "missed"
      ? { tone: "missed", text: `Ответ за ${formatDuration(sla.waited_minutes)}, норма ${formatDuration(sla.target_minutes)}` }
      : { tone: "met", text: `Ответ за ${formatDuration(sla.waited_minutes)}, в норме` };
  }
  const remaining = (Date.parse(sla.due_at) - now) / 60000;
  if (remaining < 0) return { tone: "breached", text: `Просрочено на ${formatDuration(-remaining)}` };
  if (remaining < sla.target_minutes * 0.2) return { tone: "warning", text: `Осталось ${formatDuration(remaining)}` };
  return { tone: "ok", text: `Ответить за ${formatDuration(remaining)}` };
}
