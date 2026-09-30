/** Specialist tools on top of the shared client: reply templates and first-reply SLA. */
import { request } from "../../api/client";
import type { OperatorTicket } from "../../api/types";

/** Mirrors apps/api/app/schemas/sla.py. */
export interface Sla {
  target_minutes: number;
  started_at: string;
  due_at: string;
  replied_at: string | null;
  state: "ok" | "warning" | "breached" | "met" | "missed";
  waited_minutes: number;
  remaining_minutes: number;
}

export interface SlaSummary {
  days: number;
  met: number;
  missed: number;
  breached_open: number;
  pending: number;
  met_rate: number | null;
  targets: Record<string, number>;
}

/** Mirrors apps/api/app/schemas/reply_template.py. */
export interface ReplyTemplate {
  id: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export function slaOf(ticket: OperatorTicket): Sla | null {
  return (ticket as OperatorTicket & { sla?: Sla | null }).sla ?? null;
}

export const operatorApi = {
  listTemplates(signal?: AbortSignal): Promise<ReplyTemplate[]> {
    return request("/api/operator/templates", {}, signal);
  },

  createTemplate(payload: { title: string; body: string }): Promise<ReplyTemplate> {
    return request("/api/operator/templates", { method: "POST", body: JSON.stringify(payload) });
  },

  updateTemplate(id: string, payload: { title?: string; body?: string }): Promise<ReplyTemplate> {
    return request(`/api/operator/templates/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTemplate(id: string): Promise<void> {
    return request(`/api/operator/templates/${id}`, { method: "DELETE" });
  },

  /** A first reply written from the card and from what helped colleagues; the specialist edits it. */
  replyDraft(ticketId: string): Promise<{ text: string; based_on: string | null }> {
    return request(`/api/operator/tickets/${ticketId}/draft`);
  },

  slaSummary(days: number, signal?: AbortSignal): Promise<SlaSummary> {
    return request(`/api/operator/sla?days=${days}`, {}, signal);
  },
};

/** "{имя}" becomes the employee's first name; without a name the greeting is dropped. */
export function fillTemplate(body: string, ownerName: string | null | undefined): string {
  const firstName = ownerName?.trim().split(/\s+/)[0];
  if (firstName) return body.replaceAll("{имя}", firstName);
  return body.replace(/^\{имя\}[,!]?\s*/, "").replaceAll("{имя}", "").replace(/^./, (letter) => letter.toUpperCase());
}
