import { ApiError } from "../../api/errors";
import type { Conversation } from "../../api/types";

/** The server explains a rejected message (a password, an insult) — show its words. */
export function explain(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    const detail = cause.detail;
    if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

/** When colleagues may be asked: the steps did not help, or the request waits for a specialist.
 *  The server checks the same (and security requests never reach the feed). */
export function canAskColleagues(conversation: Conversation): boolean {
  if (conversation.playbook_id === "security_incident") return false;
  if (conversation.status === "ESCALATED" || conversation.status === "IN_PROGRESS") return true;
  return conversation.status === "TROUBLESHOOTING"
    && conversation.completed_steps.some((step) => step.outcome !== "helped");
}
