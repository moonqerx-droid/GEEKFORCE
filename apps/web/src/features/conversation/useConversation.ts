import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { ApiError, ConflictError, NetworkError, NotFoundError, ValidationError } from "../../api/errors";
import type { Conversation, StepOutcome } from "../../api/types";

const STORAGE_KEY = "helpflow.conversationId";

type Phase = "idle" | "loading" | "ready" | "error";

export interface FailedMessage {
  id: number;
  content: string;
}

export interface ConversationState {
  phase: Phase;
  conversation: Conversation | null;
  error: string | null;
  notice: string | null;
  sending: boolean;
  pendingMessage: string | null;
  failedMessages: FailedMessage[];
  start: () => Promise<void>;
  startWithMessage: (content: string) => Promise<void>;
  restartFresh: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  sendStepResult: (outcome: StepOutcome) => Promise<void>;
  escalateNow: () => Promise<void>;
  retryFailedMessage: (id: number) => Promise<void>;
  rate: (rating: number, comment?: string) => Promise<void>;
  dismissNotice: () => void;
}

/** While a specialist owns the conversation, their replies arrive by polling. */
export const LIVE_STATUSES = new Set(["ESCALATED", "IN_PROGRESS"]);
export const POLL_INTERVAL_MS = 3000;

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

export function useConversation(): ConversationState {
  const [phase, setPhase] = useState<Phase>("idle");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [failedMessages, setFailedMessages] = useState<FailedMessage[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const mutationRef = useRef(false);
  const createdRef = useRef<Conversation | null>(null);
  const failedMessageIdRef = useRef(0);

  const enqueueFailedMessage = useCallback((content: string) => {
    const failed = { id: ++failedMessageIdRef.current, content };
    setFailedMessages((current) => [...current, failed]);
  }, []);

  const restore = useCallback(async () => {
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

  const startWithMessage = useCallback(async (content: string) => {
    if (mutationRef.current) return;
    mutationRef.current = true;
    setSending(true);
    setPendingMessage(content);
    setError(null);
    try {
      const created = createdRef.current ?? await api.createConversation();
      createdRef.current = created;
      storeId(created.id);
      const updated = await api.sendMessage(created.id, {
        content, expected_revision: created.revision,
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
      setError(describeError(err));
    } finally {
      mutationRef.current = false;
      setSending(false);
      setPendingMessage(null);
    }
  }, []);

  useEffect(() => {
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
    async (content: string) => {
      if (!conversation || mutationRef.current) return;
      mutationRef.current = true;
      setSending(true);
      setPendingMessage(content);
      setError(null);
      const knownMessageIds = new Set(conversation.messages.map((message) => message.id));
      try {
        const updated = await api.sendMessage(conversation.id, {
          content,
          expected_revision: conversation.revision,
        });
        setConversation(updated);
      } catch (err) {
        if (err instanceof ConflictError) {
          const fresh = await reloadAfterConflict(conversation.id);
          const alreadyCommitted = fresh?.messages.some(
            (message) =>
              message.role === "user"
              && message.content === content
              && !knownMessageIds.has(message.id),
          );
          if (!alreadyCommitted) enqueueFailedMessage(content);
        } else {
          setError(describeError(err));
          enqueueFailedMessage(content);
        }
        throw err;
      } finally {
        mutationRef.current = false;
        setSending(false);
        setPendingMessage(null);
      }
    },
    [conversation, enqueueFailedMessage, reloadAfterConflict],
  );

  const retryFailedMessage = useCallback(async (id: number) => {
    if (!conversation || mutationRef.current) return;
    const failed = failedMessages.find((message) => message.id === id);
    if (!failed) return;
    setFailedMessages((current) => current.filter((message) => message.id !== id));
    const content = failed.content;
    await sendMessage(content).catch(() => undefined);
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

  return {
    phase,
    conversation,
    error,
    notice,
    sending,
    pendingMessage,
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
