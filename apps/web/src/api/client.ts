import { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError } from "./errors";
import type {
  Conversation,
  Incident,
  MessageCreatePayload,
  OperatorTicket,
  StepResultPayload,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
export const REQUEST_TIMEOUT_MS = 12000;

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  const timer = setTimeout(cancel, REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
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
  } catch (cause) {
    if (signal?.aborted || cause instanceof ApiError) throw cause;
    if (controller.signal.aborted) {
      throw new Error("Сервер не ответил за 12 секунд. Обновите обращение перед повторной отправкой: сообщение могло сохраниться.");
    }
    throw new NetworkError("network_error", cause);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(502, "Сервер вернул некорректный ответ. Попробуйте обновить страницу.");
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
