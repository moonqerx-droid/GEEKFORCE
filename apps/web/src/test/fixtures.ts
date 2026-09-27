import type { AdminUser, Conversation, OperatorTicket, PersonalMetrics, Profile, SpecialistMetrics } from "../api/types";

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

export function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "u-anna",
    name: "Анна Смирнова",
    email: "anna@company.ru",
    department: "it",
    role: "operator",
    is_active: true,
    status: "active",
    must_change_password: false,
    revision: 3,
    created_at: "2026-09-01T09:00:00Z",
    last_login_at: "2026-09-27T18:30:00Z",
    ...overrides,
  };
}

export function makePersonalMetrics(overrides: Partial<PersonalMetrics> = {}): PersonalMetrics {
  return {
    days: 30,
    resolved: 24,
    in_progress: 2,
    waiting_first_reply: 1,
    median_first_reply_minutes: 6,
    median_resolution_minutes: 42,
    average_rating: 4.6,
    ratings_count: 15,
    ...overrides,
  };
}

export function makeSpecialistMetrics(overrides: Partial<SpecialistMetrics> = {}): SpecialistMetrics {
  return {
    ...makePersonalMetrics(),
    operator_id: "u-anna",
    operator_name: "Анна Смирнова",
    assigned: 27,
    p90_first_reply_minutes: 18,
    p90_resolution_minutes: 130,
    first_reply_sla_rate: 0.83,
    daily: [
      { date: "2026-09-26", resolved: 3 },
      { date: "2026-09-27", resolved: 5 },
    ],
    topics: [{ name: "VPN", count: 9 }, { name: "Почта", count: 4 }],
    urgency: { critical: 1, high: 6, normal: 18, low: 2 },
    ...overrides,
  };
}

export function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: "user-1",
    name: "Иван Петров",
    email: "ivan@example.ru",
    department: "sales",
    role: "employee",
    is_active: true,
    must_change_password: false,
    revision: 2,
    created_at: "2026-09-01T09:00:00Z",
    last_login_at: "2026-09-28T08:00:00Z",
    ...overrides,
  };
}
