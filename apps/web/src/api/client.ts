import { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError } from "./errors";
import type {
  AdminConversation,
  AdminUser,
  AdminUserUpdate,
  Attachment,
  AuthUser,
  ChangePasswordPayload,
  Conversation,
  Incident,
  IncidentBroadcastResult,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  KnownIssue,
  LoginPayload,
  MessageCreatePayload,
  Metrics,
  NewOperatorPayload,
  OperatorRegistrationPayload,
  OperatorTicket,
  PersonalMetrics,
  Profile,
  ProfileUpdate,
  RegistrationPayload,
  SelfHelp,
  SelfHelpPopular,
  SpecialistMetrics,
  StepResultPayload,
  TemporaryCredential,
  TicketScope,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
export const REQUEST_TIMEOUT_MS = 12000;
const configuredMutationTimeout = Number(import.meta.env.VITE_MUTATION_TIMEOUT_MS);
export const MUTATION_TIMEOUT_MS = Number.isFinite(configuredMutationTimeout)
  && configuredMutationTimeout >= 100000
  ? configuredMutationTimeout
  : 100000;

export async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  const timer = setTimeout(cancel, timeoutMs);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      credentials: "include",
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
      const seconds = Math.round(timeoutMs / 1000);
      throw new Error(`Сервер не ответил за ${seconds} секунд. Обновите обращение перед повторной отправкой: сообщение могло сохраниться.`);
    }
    throw new NetworkError("network_error", cause);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

/** Multipart upload: the browser sets the boundary, so no JSON content type here. */
async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${BASE_URL}${path}`, { method: "POST", body, credentials: "include" })
    .catch((cause) => { throw new NetworkError("network_error", cause); });
  const text = await response.text();
  const parsed = text ? safeJsonParse(text) : undefined;
  if (!response.ok) {
    const detail = parsed && typeof parsed === "object" && "detail" in parsed ? parsed.detail : parsed;
    if (response.status === 409) throw new ConflictError(detail);
    if (response.status === 422) throw new ValidationError(detail);
    if (response.status === 404) throw new NotFoundError(detail);
    throw new ApiError(response.status, `http_${response.status}`, detail);
  }
  return parsed as T;
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

  selfHelp(query: string, signal?: AbortSignal): Promise<SelfHelp> {
    return request(`/api/self-help?q=${encodeURIComponent(query)}`, {}, signal);
  },

  selfHelpPopular(signal?: AbortSignal): Promise<SelfHelpPopular> {
    return request("/api/self-help/popular", {}, signal);
  },

  knownIssues(signal?: AbortSignal): Promise<KnownIssue[]> {
    return request("/api/known-issues", {}, signal);
  },

  listConversations(signal?: AbortSignal): Promise<Conversation[]> {
    return request("/api/conversations", {}, signal);
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
      MUTATION_TIMEOUT_MS,
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
      MUTATION_TIMEOUT_MS,
    );
  },

  /** «Срочно»: straight to a specialist, top of the queue. */
  markUrgent(id: string, signal?: AbortSignal): Promise<Conversation> {
    return request(
      `/api/conversations/${id}/urgent`,
      { method: "POST" },
      signal,
      MUTATION_TIMEOUT_MS,
    );
  },

  escalate(id: string, signal?: AbortSignal): Promise<Conversation> {
    return request(
      `/api/conversations/${id}/escalate`,
      { method: "POST" },
      signal,
      MUTATION_TIMEOUT_MS,
    );
  },

  uploadAttachment(conversationId: string, file: File): Promise<Attachment> {
    return upload(`/api/conversations/${conversationId}/attachments`, file);
  },

  uploadTicketAttachment(conversationId: string, file: File): Promise<Attachment> {
    return upload(`/api/operator/tickets/${conversationId}/attachments`, file);
  },

  rateConversation(id: string, rating: number, comment?: string): Promise<Conversation> {
    return request(`/api/conversations/${id}/rating`, {
      method: "POST", body: JSON.stringify({ rating, comment }),
    });
  },

  listTickets(scope: TicketScope = "queue", signal?: AbortSignal): Promise<OperatorTicket[]> {
    return request(`/api/operator/tickets?scope=${scope}`, {}, signal);
  },

  getTicket(id: string, signal?: AbortSignal): Promise<OperatorTicket> {
    return request(`/api/operator/tickets/${id}`, {}, signal);
  },

  assignTicket(id: string): Promise<OperatorTicket> {
    return request(`/api/operator/tickets/${id}/assign`, { method: "POST" });
  },

  replyToTicket(id: string, content: string, attachment_ids: string[] = []): Promise<OperatorTicket> {
    return request(`/api/operator/tickets/${id}/messages`, {
      method: "POST", body: JSON.stringify(attachment_ids.length ? { content, attachment_ids } : { content }),
    });
  },

  resolveTicket(id: string, summary: string): Promise<OperatorTicket> {
    return request(`/api/operator/tickets/${id}/resolve`, {
      method: "POST", body: JSON.stringify({ summary }),
    });
  },

  metrics(days: number, signal?: AbortSignal): Promise<Metrics> {
    return request(`/api/admin/metrics?days=${days}`, {}, signal);
  },

  listUsers(signal?: AbortSignal): Promise<AdminUser[]> {
    return request("/api/admin/users", {}, signal);
  },

  createOperator(payload: NewOperatorPayload): Promise<TemporaryCredential> {
    return request("/api/admin/users/operators", { method: "POST", body: JSON.stringify(payload) });
  },

  updateUser(id: string, payload: AdminUserUpdate): Promise<AdminUser> {
    return request(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  resetUserPassword(id: string): Promise<TemporaryCredential> {
    return request(`/api/admin/users/${id}/reset-password`, { method: "POST" });
  },

  userMetrics(id: string, days: number, signal?: AbortSignal): Promise<SpecialistMetrics> {
    return request(`/api/admin/users/${id}/metrics?days=${days}`, {}, signal);
  },

  profile(signal?: AbortSignal): Promise<Profile> {
    return request("/api/profile", {}, signal);
  },

  updateProfile(payload: ProfileUpdate): Promise<Profile> {
    return request("/api/profile", { method: "PATCH", body: JSON.stringify(payload) });
  },

  profileMetrics(days: number, signal?: AbortSignal): Promise<PersonalMetrics> {
    return request(`/api/profile/metrics?days=${days}`, {}, signal);
  },

  changePassword(payload: ChangePasswordPayload): Promise<void> {
    return request("/api/auth/change-password", { method: "POST", body: JSON.stringify(payload) });
  },

  listIncidents(signal?: AbortSignal): Promise<Incident[]> {
    return request("/api/operator/incidents", {}, signal);
  },

  confirmIncident(id: string, expected_revision: number): Promise<Incident> {
    return request(`/api/operator/incidents/${id}/confirm`, {
      method: "POST", body: JSON.stringify({ expected_revision }),
    });
  },

  broadcastIncident(id: string, message: string, expected_revision: number): Promise<IncidentBroadcastResult> {
    // One key per click: a retried request is not delivered twice.
    const request_key = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    return request(`/api/operator/incidents/${id}/broadcast`, {
      method: "POST", body: JSON.stringify({ message, request_key, expected_revision }),
    });
  },

  resolveIncident(id: string, message: string, expected_revision: number): Promise<Incident> {
    return request(`/api/operator/incidents/${id}/resolve`, {
      method: "POST", body: JSON.stringify({ message, expected_revision }),
    });
  },

  listKnowledgeDocuments(signal?: AbortSignal): Promise<KnowledgeDocument[]> {
    return request("/api/admin/knowledge/documents", {}, signal);
  },

  getKnowledgeDocument(id: string, signal?: AbortSignal): Promise<KnowledgeDocumentDetail> {
    return request(`/api/admin/knowledge/documents/${id}`, {}, signal);
  },

  /** The server extracts the text right away: the answer is already "ready" or "failed". */
  uploadKnowledgeDocument(file: File): Promise<KnowledgeDocument> {
    return upload("/api/admin/knowledge/documents", file);
  },

  deleteKnowledgeDocument(id: string): Promise<void> {
    return request(`/api/admin/knowledge/documents/${id}`, { method: "DELETE" });
  },

  listAdminConversations(query: string, signal?: AbortSignal): Promise<AdminConversation[]> {
    const params = new URLSearchParams(query.trim() ? { q: query.trim() } : {});
    return request(`/api/admin/conversations?${params}`, {}, signal);
  },

  /** Removes the conversation with its messages and attachments; there is no undo. */
  deleteAdminConversation(id: string): Promise<void> {
    return request(`/api/admin/conversations/${id}`, { method: "DELETE" });
  },

  me(signal?: AbortSignal): Promise<AuthUser> {
    return request("/api/auth/me", {}, signal);
  },

  login(payload: LoginPayload, signal?: AbortSignal): Promise<AuthUser> {
    return request("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }, signal);
  },

  logout(signal?: AbortSignal): Promise<void> {
    return request("/api/auth/logout", { method: "POST" }, signal);
  },

  register(payload: RegistrationPayload, signal?: AbortSignal): Promise<AuthUser> {
    return request("/api/auth/register", { method: "POST", body: JSON.stringify(payload) }, signal);
  },

  registerOperator(payload: OperatorRegistrationPayload, signal?: AbortSignal): Promise<AuthUser> {
    return request("/api/auth/operator/register", { method: "POST", body: JSON.stringify(payload) }, signal);
  },

  verifyEmail(email: string, code: string, signal?: AbortSignal): Promise<void> {
    return request("/api/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code }) }, signal);
  },

  resendVerification(email: string, signal?: AbortSignal): Promise<{ code: string }> {
    return request("/api/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }) }, signal);
  },

  forgotPassword(email: string, signal?: AbortSignal): Promise<{ code: string }> {
    return request("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }, signal);
  },

  resetPassword(token: string, password: string, password_confirmation: string, signal?: AbortSignal): Promise<void> {
    return request("/api/auth/reset-password", {
      method: "POST", body: JSON.stringify({ token, password, password_confirmation }),
    }, signal);
  },
};

export { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError };
