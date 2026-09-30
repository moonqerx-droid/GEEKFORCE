import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import { makeConversation } from "./fixtures";

export const handlers = [
  http.get("*/health", () => HttpResponse.json({ status: "ok" })),

  http.post("*/api/conversations", () => HttpResponse.json(makeConversation(), { status: 201 })),

  http.get("*/api/conversations", () => HttpResponse.json([])),
  http.get("*/api/known-issues", () => HttpResponse.json([])),
  http.get("*/api/self-help/popular", () => HttpResponse.json({ codes: [], topics: [] })),

  http.get("*/api/conversations/:id", ({ params }) =>
    HttpResponse.json(makeConversation({ id: params.id as string })),
  ),

  http.post("*/api/conversations/:id/messages", ({ params }) =>
    HttpResponse.json(makeConversation({ id: params.id as string, revision: 2 })),
  ),

  http.post("*/api/conversations/:id/step-result", ({ params }) =>
    HttpResponse.json(makeConversation({ id: params.id as string, revision: 2 })),
  ),

  http.post("*/api/conversations/:id/escalate", ({ params }) =>
    HttpResponse.json(makeConversation({ id: params.id as string, status: "ESCALATED" })),
  ),

  http.get("*/api/operator/tickets", () => HttpResponse.json([])),

  http.get("*/api/operator/incidents", () => HttpResponse.json([])),

  http.get("*/api/operator/templates", () => HttpResponse.json([])),

  http.get("*/api/operator/sla", () => HttpResponse.json({
    days: 7, met: 0, missed: 0, breached_open: 0, pending: 0, met_rate: null,
    targets: { critical: 15, high: 60, normal: 240, low: 240 },
  })),
];

export const server = setupServer(...handlers);
