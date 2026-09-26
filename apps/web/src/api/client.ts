import { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError } from "./errors";
import type {
  Conversation,
  Incident,
  MessageCreatePayload,
  OperatorTicket,
  StepResultPayload,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new NetworkError("network_error", cause);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const body = text ? safeJsonParse(text) : undefined;

  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : body;
    if (response.status === 409) throw new ConflictError(detail);
    if (response.status === 422) throw new ValidationError(detail);
    if (response.status === 404) throw new NotFoundError(detail);
    throw new ApiError(response.status, `http_${response.status}`, detail);
  }

  return body as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  health(signal?: AbortSignal): Promise<{ status?: string }> {
    return request("/health", {}, signal);
  },

  createConversation(signal?: AbortSignal): Promise<Conversation> {
    return request("/api/conversations", { method: "POST" }, signal);
  },

  getConversation(id: string, signal?: AbortSignal): Promise<Conversation> {
    return request(`/api/conversations/${id}`, {}, signal);
  },

  sendMessage(
    id: string,
    payload: MessageCreatePayload,
    signal?: AbortSignal,
  ): Promise<Conversation> {
    return request(
      `/api/conversations/${id}/messages`,
      { method: "POST", body: JSON.stringify(payload) },
      signal,
    );
  },

  sendStepResult(
    id: string,
    payload: StepResultPayload,
    signal?: AbortSignal,
  ): Promise<Conversation> {
    return request(
      `/api/conversations/${id}/step-result`,
      { method: "POST", body: JSON.stringify(payload) },
      signal,
    );
  },

  escalate(id: string, signal?: AbortSignal): Promise<Conversation> {
    return request(`/api/conversations/${id}/escalate`, { method: "POST" }, signal);
  },

  listTickets(signal?: AbortSignal): Promise<OperatorTicket[]> {
    return request("/api/operator/tickets", {}, signal);
  },

  /**
   * Incident Radar backend is still being designed (see PROJECT_PLAN.md).
   * Callers must treat a 404 as "feature not available yet" and hide the
   * section silently — never fabricate incidents in production code.
   */
  listIncidents(signal?: AbortSignal): Promise<Incident[]> {
    return request("/api/operator/incidents", {}, signal);
  },
};

export { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError };
