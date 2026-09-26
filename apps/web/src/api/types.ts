// Types mirror apps/api/app/schemas/conversation.py on origin/feat/backend-workflow.
// Do not invent fields — verify against /openapi.json if the backend contract changes.

export type ConversationStatus =
  | "NEW"
  | "ANALYZING"
  | "CLARIFYING"
  | "TROUBLESHOOTING"
  | "VERIFYING"
  | "RESOLVED"
  | "ESCALATED";

export type Urgency = "low" | "normal" | "high" | "critical";

export type MessageRole = "user" | "assistant" | "system";

export type StepOutcome = "helped" | "not_helped" | "cannot_perform";

export interface Message {
  id: number;
  role: MessageRole;
  content: string;
  created_at: string;
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
}

export interface OperatorTicket extends Conversation {
  original_request: string;
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

// Incident Radar — backend endpoint is still being designed. The shape below
// is a best-effort guess for local fixtures/tests only; production code must
// never assume it is correct beyond checking that a 200 response is JSON.
export interface Incident {
  id: string;
  title: string;
  service: string | null;
  conversation_ids: string[];
  created_at: string;
  summary: string | null;
}
