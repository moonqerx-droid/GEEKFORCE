import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError } from "../../api/errors";
import type { Conversation, StepOutcome } from "../../api/types";
import { takeScenario } from "../../lib/scenario";

const STORAGE_KEY = "helpflow.conversationId";

type Phase = "idle" | "loading" | "ready" | "error";

export interface FailedMessage {
  id: number;
  content: string;
  /** Files already uploaded for this message: a retry reuses them instead of uploading again. */
  attachmentIds?: string[];
}

export interface ConversationState {
  phase: Phase;
  conversation: Conversation | null;
  error: string | null;
  notice: string | null;
  sending: boolean;
  pendingMessage: string | null;
  pendingFiles: string[];
  failedMessages: FailedMessage[];
  start: () => Promise<void>;
  startWithMessage: (content: string, files?: File[]) => Promise<void>;
  restartFresh: () => Promise<void>;
  sendMessage: (content: string, files?: File[]) => Promise<void>;
  sendStepResult: (outcome: StepOutcome) => Promise<void>;
  escalateNow: () => Promise<void>;
  retryFailedMessage: (id: number) => Promise<void>;
  rate: (rating: number, comment?: string) => Promise<void>;
  dismissNotice: () => void;
  /** Continue in the earlier open request about the same problem; this one is removed. */
  mergeIntoSimilar: () => Promise<void>;
}

/** While a specialist owns the conversation, their replies arrive by polling. */
export const LIVE_STATUSES = new Set(["ESCALATED", "IN_PROGRESS"]);
export const POLL_INTERVAL_MS = 3000;

function readStartFresh(): boolean {
  try {
    return new URLSearchParams(window.location.search).has("new");
  } catch {
    return false;
  }
}

function readRequestedId(): string | null {
  try {
    return new URLSearchParams(window.location.search).get("conversation");
  } catch {
    return null;
  }
}

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage unavailable (private mode, etc.) — degrade silently.
  }
}

function describeError(err: unknown): string {
  if (err instanceof ConflictError) return "Обращение изменилось. Проверьте историю перед повторной отправкой.";
  if (err instanceof ValidationError) return "Проверьте сообщение: от 1 до 4000 символов.";
  if (err instanceof NotFoundError) return "Обращение не найдено. Начните новое обращение.";
  if (err instanceof ApiError && err.status >= 500) return "Ошибка сервера. Текст сохранён, попробуйте ещё раз.";
  if (err instanceof NetworkError) {
    return "Не удаётся связаться с сервером. Проверьте подключение и попробуйте снова.";
  }
  if (err instanceof Error) {
    return err.message || "Произошла ошибка. Попробуйте ещё раз.";
  }
  return "Произошла ошибка. Попробуйте ещё раз.";
}

class UploadFailed extends Error {}

function describeUpload(err: unknown, file: File): string {
  if (err instanceof ApiError) {
    const detail = typeof err.detail === "string" ? err.detail : null;
    if (err.status === 413) return `${file.name}: файл больше 10 МБ`;
    if (detail) return `${file.name}: ${detail}`;
  }
  if (err instanceof NetworkError) return "Не удаётся загрузить файл: нет связи с сервером. Текст и файлы сохранены.";
  return `${file.name}: не удалось загрузить. Попробуйте ещё раз.`;
}

/** Upload one by one so a refusal names the exact file; the message is sent only after all succeed. */
async function uploadAll(conversationId: string, files: File[]): Promise<string[]> {
  const ids: string[] = [];
  for (const file of files) {
    try {
      ids.push((await api.uploadAttachment(conversationId, file)).id);
    } catch (err) {
      throw new UploadFailed(describeUpload(err, file));
    }
  }
  return ids;
}

export function useConversation(): ConversationState {
  const [phase, setPhase] = useState<Phase>("idle");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [pendingFiles, setPendingFiles] = useState<string[]>([]);
  const [failedMessages, setFailedMessages] = useState<FailedMessage[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const mutationRef = useRef(false);
  const createdRef = useRef<Conversation | null>(null);
  const failedMessageIdRef = useRef(0);

  const enqueueFailedMessage = useCallback((content: string, attachmentIds: string[] = []) => {
    const failed = { id: ++failedMessageIdRef.current, content, attachmentIds };
    setFailedMessages((current) => [...current, failed]);
  }, []);

  const restore = useCallback(async () => {
    if (readStartFresh()) {
      storeId(null);
      try {
        // Drop the one-off flag so a reload keeps the conversation that starts next.
        window.history.replaceState(window.history.state, "", window.location.pathname);
      } catch {
        // History API unavailable — the flag only matters on reload.
      }
    }
    const requestedId = readRequestedId();
    if (requestedId) storeId(requestedId);
    const storedId = requestedId ?? readStoredId();
    if (!storedId) {
      setPhase("ready");
      return;
    }
    setPhase("loading");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await api.getConversation(storedId, controller.signal);
      if (controller.signal.aborted) return;
      // A finished, rated conversation is history; coming back to the page means a new problem.
      // Unrated ones stay so the employee can still rate after a reload.
      if (data.status === "RESOLVED" && data.rating != null && !requestedId) {
        storeId(null);
        setPhase("ready");
        return;
      }
      setConversation(data);
      setPhase("ready");
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof NotFoundError) {
        storeId(null);
        setConversation(null);
        setPhase("ready");
      } else {
        setError(describeError(err));
        setPhase("error");
      }
    }
  }, []);

  const startWithMessage = useCallback(async (content: string, files: File[] = []) => {
    if (mutationRef.current) return;
    mutationRef.current = true;
    setSending(true);
    setPendingMessage(content);
    setPendingFiles(files.map((file) => file.name));
    setError(null);
    try {
      const created = createdRef.current ?? await api.createConversation();
      createdRef.current = created;
      storeId(created.id);
      const attachmentIds = await uploadAll(created.id, files);
      const updated = await api.sendMessage(created.id, {
        content, expected_revision: created.revision,
        ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
      });
      setConversation(updated);
      createdRef.current = null;
      setPhase("ready");
    } catch (err) {
      if (err instanceof ConflictError && createdRef.current) {
        // The previous request may have committed before its response was lost.
        const fresh = await api.getConversation(createdRef.current.id).catch(() => null);
        if (fresh) {
          setConversation(fresh);
          createdRef.current = null;
        }
      }
      setError(err instanceof UploadFailed ? err.message : describeError(err));
      // The composer keeps the text and files only when the send is reported as failed.
      throw err;
    } finally {
      mutationRef.current = false;
      setSending(false);
      setPendingMessage(null);
      setPendingFiles([]);
    }
  }, []);

  const startWithMessageRef = useRef<(content: string, files?: File[]) => Promise<void>>(async () => undefined);

  useEffect(() => {
    // A case scenario picked on the login page opens as a fresh request with its words already sent.
    const scenario = takeScenario();
    if (scenario) {
      storeId(null);
      setPhase("ready");
      void startWithMessageRef.current(scenario, []).catch(() => undefined);
      return () => abortRef.current?.abort();
    }
    void restore();
    return () => abortRef.current?.abort();
  }, [restore]);

  const start = useCallback(async () => {
    setPhase("loading");
    setError(null);
    try {
      const data = await api.createConversation();
      storeId(data.id);
      setConversation(data);
      setPhase("ready");
    } catch (err) {
      setError(describeError(err));
      setPhase("error");
    }
  }, []);

  const restartFresh = useCallback(async () => {
    if (mutationRef.current) return;
    storeId(null);
    try {
      if (readRequestedId()) window.history.replaceState(null, "", window.location.pathname);
    } catch {
      // History API unavailable — the stale query only matters on reload.
    }
    createdRef.current = null;
    setFailedMessages([]);
    setError(null);
    setConversation(null);
    setPhase("ready");
  }, []);

  const reloadAfterConflict = useCallback(async (id: string) => {
    try {
      const fresh = await api.getConversation(id);
      setConversation(fresh);
      setNotice("Обращение изменилось в другой вкладке. Мы загрузили актуальное состояние.");
      return fresh;
    } catch (err) {
      setError(describeError(err));
      return null;
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string, files: File[] = [], reuseIds: string[] = []) => {
      if (!conversation || mutationRef.current) return;
      mutationRef.current = true;
      setSending(true);
      setPendingMessage(content);
      setPendingFiles(files.map((file) => file.name));
      setError(null);
      const knownMessageIds = new Set(conversation.messages.map((message) => message.id));
      let attachmentIds = reuseIds;
      try {
        attachmentIds = [...reuseIds, ...await uploadAll(conversation.id, files)];
        const updated = await api.sendMessage(conversation.id, {
          content,
          expected_revision: conversation.revision,
          ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
        });
        setConversation(updated);
      } catch (err) {
        if (err instanceof UploadFailed) {
          // Nothing was sent: the composer keeps the text and the files for another try.
          setError(err.message);
        } else if (err instanceof ConflictError) {
          const fresh = await reloadAfterConflict(conversation.id);
          const alreadyCommitted = fresh?.messages.some(
            (message) =>
              message.role === "user"
              && message.content === content
              && !knownMessageIds.has(message.id),
          );
          if (!alreadyCommitted) enqueueFailedMessage(content, attachmentIds);
        } else {
          setError(describeError(err));
          enqueueFailedMessage(content, attachmentIds);
        }
        throw err;
      } finally {
        mutationRef.current = false;
        setSending(false);
        setPendingMessage(null);
        setPendingFiles([]);
      }
    },
    [conversation, enqueueFailedMessage, reloadAfterConflict],
  );

  const retryFailedMessage = useCallback(async (id: number) => {
    if (!conversation || mutationRef.current) return;
    const failed = failedMessages.find((message) => message.id === id);
    if (!failed) return;
    setFailedMessages((current) => current.filter((message) => message.id !== id));
    await sendMessage(failed.content, [], failed.attachmentIds ?? []).catch(() => undefined);
  }, [conversation, failedMessages, sendMessage]);

  const sendStepResult = useCallback(
    async (outcome: StepOutcome) => {
      if (!conversation || mutationRef.current) return;
      mutationRef.current = true;
      setSending(true);
      setError(null);
      try {
        const updated = await api.sendStepResult(conversation.id, {
          outcome,
          expected_revision: conversation.revision,
          step_code: conversation.current_step?.code,
        });
        setConversation(updated);
      } catch (err) {
        if (err instanceof ConflictError) {
          await reloadAfterConflict(conversation.id);
        } else {
          setError(describeError(err));
        }
      } finally {
        mutationRef.current = false;
        setSending(false);
      }
    },
    [conversation, reloadAfterConflict],
  );

  const escalateNow = useCallback(async () => {
    if (!conversation || mutationRef.current) return;
    mutationRef.current = true;
    setSending(true);
    setError(null);
    try {
      const updated = await api.escalate(conversation.id);
      setConversation(updated);
    } catch (err) {
      if (err instanceof ConflictError) {
        await reloadAfterConflict(conversation.id);
      } else {
        setError(describeError(err));
      }
    } finally {
      mutationRef.current = false;
      setSending(false);
    }
  }, [conversation, reloadAfterConflict]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  const liveId = conversation && LIVE_STATUSES.has(conversation.status) ? conversation.id : null;
  useEffect(() => {
    if (!liveId) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      if (mutationRef.current) return;
      api.getConversation(liveId, controller.signal)
        .then((fresh) => {
          setConversation((current) => (
            current && current.id === fresh.id && current.revision === fresh.revision
              && current.messages.length === fresh.messages.length
              ? current
              : fresh
          ));
        })
        .catch(() => undefined);
    }, POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [liveId]);

  const rate = useCallback(async (rating: number, comment?: string) => {
    if (!conversation) return;
    setError(null);
    try {
      setConversation(await api.rateConversation(conversation.id, rating, comment));
    } catch (err) {
      setError(describeError(err));
    }
  }, [conversation]);

  const mergeIntoSimilar = useCallback(async () => {
    if (!conversation?.similar_open || mutationRef.current) return;
    mutationRef.current = true;
    setSending(true);
    try {
      const target = await api.mergeIntoSimilar(conversation.id);
      createdRef.current = null;
      storeId(target.id);
      try {
        window.history.replaceState(window.history.state, "", `${window.location.pathname}?conversation=${target.id}`);
      } catch {
        // History API unavailable — the stored id still opens the right request on reload.
      }
      setConversation(target);
    } catch (err) {
      setError(describeError(err));
    } finally {
      mutationRef.current = false;
      setSending(false);
    }
  }, [conversation]);

  startWithMessageRef.current = startWithMessage;

  return {
    mergeIntoSimilar,
    phase,
    conversation,
    error,
    notice,
    sending,
    pendingMessage,
    pendingFiles,
    failedMessages,
    start,
    startWithMessage,
    restartFresh,
    sendMessage,
    sendStepResult,
    escalateNow,
    retryFailedMessage,
    rate,
    dismissNotice,
  };
}
