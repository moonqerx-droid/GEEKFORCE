import type { Colleague, PeerHelpRequest } from "../../api/types";

export const ME: Colleague = { id: "user-1", name: "Иван Петров", department: "sales", helped_count: 0 };
export const ELENA: Colleague = { id: "emp-elena", name: "Елена Соколова", department: "marketing", helped_count: 2 };

export function makePeerHelp(overrides: Partial<PeerHelpRequest> = {}): PeerHelpRequest {
  return {
    id: "peer-1",
    conversation_id: "conv-1",
    title: "VPN подключается, но портал не открывается",
    area: "VPN",
    status: "OPEN",
    author: ELENA,
    helper: null,
    messages: [],
    created_at: "2026-10-01T09:00:00Z",
    updated_at: "2026-10-01T09:00:00Z",
    ...overrides,
  };
}
