import { useEffect, useRef } from "react";
import type { Message } from "../api/types";

const BASE_TITLE = "HelpFlow";

/**
 * While the tab is in the background, the title counts new specialist replies —
 * «(1) Ответ специалиста — HelpFlow» — the way messengers do, so nobody has to keep checking.
 */
export function useTabNotice(messages: Message[]) {
  const seen = useRef<Set<number> | null>(null);
  const latest = useRef(messages);

  const operatorIds = (list: Message[]) => list.filter((m) => m.role === "operator").map((m) => m.id);

  useEffect(() => {
    latest.current = messages;
    if (seen.current === null || !document.hidden) {
      seen.current = new Set(operatorIds(messages));
      document.title = BASE_TITLE;
      return;
    }
    const fresh = operatorIds(messages).filter((id) => !seen.current?.has(id)).length;
    document.title = fresh ? `(${fresh}) Ответ специалиста — ${BASE_TITLE}` : BASE_TITLE;
  }, [messages]);

  useEffect(() => {
    const onVisible = () => {
      if (document.hidden) return;
      seen.current = new Set(operatorIds(latest.current));
      document.title = BASE_TITLE;
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      document.title = BASE_TITLE;
    };
  }, []);
}
