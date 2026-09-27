// Types mirror apps/api/app/schemas/conversation.py on origin/feat/backend-workflow.
// Do not invent fields — verify against /openapi.json if the backend contract changes.

export type ConversationStatus =
  | "NEW"
  | "ANALYZING"
  | "CLARIFYING"
  | "TROUBLESHOOTING"
  | "VERIFYING"
  | "RESOLVED"
  | "ESCALATED"
  | "IN_PROGRESS";

export type Urgency = "low" | "normal" | "high" | "critical";

export type MessageRole = "user" | "assistant" | "system" | "operator";

export type StepOutcome = "helped" | "not_helped" | "cannot_perform";

export interface Message {
  id: number;
  role: MessageRole;
  content: string;
  created_at: string;
  author_name?: string | null;
}

export interface CompletedStep {
  id: number;
  code: string;
  instruction: string;
  outcome: StepOutcome;
  position: number;
  created_at: string;
}

export interface CurrentStep {
  code: string;
  instruction: string;
}

export interface Conversation {
  id: string;
  revision: number;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
  summary: string | null;
  service: string | null;
  symptoms: string[];
  urgency: Urgency;
  urgency_reason: string | null;
  known_facts: Record<string, string>;
  missing_facts: string[];
  confidence: number | null;
  playbook_id: string | null;
  messages: Message[];
  completed_steps: CompletedStep[];
  current_step: CurrentStep | null;
  escalation_summary: string | null;
  escalation_card: Record<string, unknown> | null;
  incident_id: string | null;
  rag_source_ids: string[];
  ai_fallback_reason: string | null;
  ai_latency_ms: number | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  escalated_at?: string | null;
  assigned_at?: string | null;
  first_operator_reply_at?: string | null;
  resolved_at?: string | null;
  resolved_by?: "assistant" | "operator" | null;
  rating?: number | null;
  rating_comment?: string | null;
}

export interface OperatorTicket extends Conversation {
  original_request: string;
  owner_name?: string | null;
  owner_department?: Department | null;
}

export type TicketScope = "queue" | "mine" | "resolved";

/** Mirrors helpflow_ai.schemas.EscalationCard. */
export interface EscalationCard {
  original_request: string;
  summary: string;
  service: string;
  urgency: string;
  urgency_reason: string;
  known_facts: Record<string, string>;
  questions_and_answers: { question?: string; answer?: string }[];
  performed_steps: { step_id?: string; step?: string; result?: string }[];
  current_result: string;
  escalation_reason: string;
  recommended_team: string;
  ai_summary: string;
}

export interface TeamMember {
  id: string;
  email: string;
  name: string;
  role: "operator" | "admin";
  status: "active" | "disabled" | "invited";
  created_at: string;
  last_login_at: string | null;
}

export interface InviteResult {
  invite_url: string;
  expires_at: string;
  email_sent: boolean;
}

export interface DailyMetric {
  date: string;
  assistant: number;
  operator: number;
  open: number;
  total: number;
}

export interface ProblemMetric {
  playbook_id: string;
  service: string | null;
  count: number;
  escalation_rate: number;
}

export interface OperatorLoad {
  id: string;
  name: string;
  is_active: boolean;
  in_progress: number;
  resolved: number;
  median_resolution_minutes: number | null;
  average_rating: number | null;
}

export interface Metrics {
  days: number;
  total: number;
  resolved_by_assistant: number;
  resolved_by_operator: number;
  open: number;
  waiting: number;
  self_service_rate: number | null;
  median_resolution_minutes: number | null;
  median_first_reply_minutes: number | null;
  average_rating: number | null;
  ratings_count: number;
  daily: DailyMetric[];
  top_problems: ProblemMetric[];
  urgency: Record<Urgency, number>;
  operators: OperatorLoad[];
}

export interface MessageCreatePayload {
  content: string;
  expected_revision?: number;
}

export interface StepResultPayload {
  outcome: StepOutcome;
  expected_revision?: number;
  step_code?: string;
}

/** Mirrors apps/api/app/schemas/incident.py. */
export type IncidentStatus = "CANDIDATE" | "ACTIVE" | "RESOLVED";

export interface IncidentMember {
  id: string;
  status: ConversationStatus;
  owner_name: string | null;
  owner_department: Department | null;
  original_request: string;
  created_at: string;
}

export interface IncidentUpdate {
  message: string;
  request_key: string;
  created_at: string;
}

export interface Incident {
  id: string;
  status: IncidentStatus;
  service: string;
  title: string;
  signature_tokens: string[];
  evidence_tokens: string[];
  similarity_threshold: number;
  revision: number;
  created_at: string;
  updated_at: string;
  conversation_count: number;
  conversation_ids: string[];
  latest_update: IncidentUpdate | null;
  service_label?: string | null;
  affected_employees?: number;
  first_seen_at?: string | null;
  members?: IncidentMember[];
}

export interface IncidentBroadcastResult {
  incident: Incident;
  delivered_to: string[];
}

export type UserRole = "employee" | "operator" | "admin";
export type Department = "it" | "sales" | "marketing" | "finance" | "hr" | "operations" | "other";

export interface AuthUser {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  department: Department;
  role: UserRole;
  email_verified_at: string | null;
}

export interface LoginPayload {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface RegistrationPayload {
  first_name: string;
  last_name: string;
  email: string;
  department: Department | "";
  password: string;
  password_confirmation: string;
  accepted_terms: boolean;
}

export type OperatorRegistrationPayload = Omit<RegistrationPayload, "accepted_terms"> & {
  invite_token: string;
};
