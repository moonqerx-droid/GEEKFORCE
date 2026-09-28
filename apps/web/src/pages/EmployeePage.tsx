import { useCallback, useState } from "react";
import { useLocation } from "react-router-dom";
import type { Conversation } from "../api/types";
import { ConversationPage } from "../features/conversation/ConversationPage";
import { RequestRail } from "../features/conversation/RequestRail";
import "./EmployeePage.css";

/** Messenger-style desk: own requests on the left, the open one in the middle. */
export function EmployeePage() {
  const location = useLocation();
  const [current, setCurrent] = useState<{ id: string | null; tick: number }>({ id: null, tick: 0 });

  const onActivity = useCallback((conversation: Conversation | null) => {
    setCurrent((prev) => ({ id: conversation?.id ?? null, tick: prev.tick + 1 }));
  }, []);

  return (
    <div className="desk">
      <RequestRail currentId={current.id} refreshKey={current.tick} />
      {/* Every navigation here (list, menu, history link) opens the chat afresh. */}
      <ConversationPage key={location.key} onActivity={onActivity} />
    </div>
  );
}
