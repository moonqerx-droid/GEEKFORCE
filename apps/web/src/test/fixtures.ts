import type { Conversation, Incident, OperatorTicket } from "../api/types";

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

export function makeMessage(role: "user" | "assistant" | "system" | "operator", content: string) {
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

export function makeIncident(overrides: Partial<Incident> = {}): Incident {
  const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60000).toISOString();
  const people: [string, string, string, number][] = [
    ["c1", "Иван Петров", "VPN не подключается, пишет ошибку 809", 28],
    ["c2", "Елена Соколова", "Не могу подключиться к VPN из дома, ошибка 809", 22],
    ["c3", "Дмитрий Волков", "VPN не подключается с утра, выдаёт ошибку 809", 16],
    ["c4", "Ольга Морозова", "Не подключается VPN, ошибка 809, а у меня отчёт горит", 9],
  ];
  return {
    id: "inc-1",
    status: "CANDIDATE",
    service: "vpn",
    service_label: "VPN",
    title: "Массовая недоступность VPN",
    signature_tokens: ["809", "vpn", "подключается"],
    evidence_tokens: ["809", "vpn", "подключается"],
    similarity_threshold: 0.55,
    revision: 3,
    created_at: minutesAgo(16),
    updated_at: minutesAgo(9),
    conversation_count: people.length,
    conversation_ids: people.map(([id]) => id),
    latest_update: null,
    affected_employees: people.length,
    first_seen_at: minutesAgo(28),
    members: people.map(([id, owner_name, original_request, minutes]) => ({
      id, owner_name, owner_department: "sales", original_request, status: "ESCALATED", created_at: minutesAgo(minutes),
    })),
    ...overrides,
  };
}
