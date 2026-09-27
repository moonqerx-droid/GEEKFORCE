import type { Conversation, OperatorTicket } from "../api/types";

let nextMessageId = 1;

export function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "conv-1",
    revision: 1,
    status: "NEW",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    summary: null,
    service: null,
    symptoms: [],
    urgency: "normal",
    urgency_reason: null,
    known_facts: {},
    missing_facts: [],
    confidence: null,
    playbook_id: null,
    messages: [],
    completed_steps: [],
    current_step: null,
    escalation_summary: null,
    escalation_card: null,
    incident_id: null,
    rag_source_ids: [],
    ai_fallback_reason: null,
    ai_latency_ms: null,
    ...overrides,
  };
}

export function makeMessage(role: "user" | "assistant" | "system", content: string) {
  return {
    id: nextMessageId++,
    role,
    content,
    created_at: new Date().toISOString(),
  };
}

export function makeTicket(overrides: Partial<OperatorTicket> = {}): OperatorTicket {
  return {
    ...makeConversation({ status: "ESCALATED" }),
    original_request: "Не могу войти в CRM",
    ...overrides,
  };
}
