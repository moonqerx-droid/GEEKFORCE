import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { ConflictError, NetworkError } from "../../api/errors";
import type { Conversation, StepOutcome } from "../../api/types";

const STORAGE_KEY = "helpflow.conversationId";

type Phase = "idle" | "loading" | "ready" | "error";

export interface ConversationState {
  phase: Phase;
  conversation: Conversation | null;
  error: string | null;
  notice: string | null;
  sending: boolean;
  start: () => Promise<void>;
  restartFresh: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  sendStepResult: (outcome: StepOutcome) => Promise<void>;
  escalateNow: () => Promise<void>;
  dismissNotice: () => void;
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
  const abortRef = useRef<AbortController | null>(null);

  const restore = useCallback(async () => {
    const storedId = readStoredId();
    if (!storedId) {
      setPhase("ready");
      return;
    }
    setPhase("loading");
    try {
      const controller = new AbortController();
      abortRef.current = controller;
      const data = await api.getConversation(storedId, controller.signal);
      setConversation(data);
      setPhase("ready");
    } catch (err) {
      // A stored id that the backend no longer knows about shouldn't block
      // the welcome screen — just drop it and start fresh.
      storeId(null);
      setConversation(null);
      setPhase("ready");
      void err;
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
    storeId(null);
    setConversation(null);
    await start();
  }, [start]);

  const reloadAfterConflict = useCallback(async (id: string) => {
    try {
      const fresh = await api.getConversation(id);
      setConversation(fresh);
      setNotice("Обращение изменилось в другой вкладке. Мы загрузили актуальное состояние.");
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!conversation || sending) return;
      setSending(true);
      setError(null);
      try {
        const updated = await api.sendMessage(conversation.id, {
          content,
          expected_revision: conversation.revision,
        });
        setConversation(updated);
      } catch (err) {
        if (err instanceof ConflictError) {
          await reloadAfterConflict(conversation.id);
        } else {
          setError(describeError(err));
        }
        throw err;
      } finally {
        setSending(false);
      }
    },
    [conversation, sending, reloadAfterConflict],
  );

  const sendStepResult = useCallback(
    async (outcome: StepOutcome) => {
      if (!conversation || sending) return;
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
        setSending(false);
      }
    },
    [conversation, sending, reloadAfterConflict],
  );

  const escalateNow = useCallback(async () => {
    if (!conversation || sending) return;
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
      setSending(false);
    }
  }, [conversation, sending, reloadAfterConflict]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    phase,
    conversation,
    error,
    notice,
    sending,
    start,
    restartFresh,
    sendMessage,
    sendStepResult,
    escalateNow,
    dismissNotice,
  };
}
