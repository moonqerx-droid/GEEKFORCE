import { useState } from "react";
import type { Conversation } from "../api/types";
import "./DebugPanel.css";

export function DebugPanel({ conversation }: { conversation: Conversation }) {
  const [open, setOpen] = useState(false);
  if (import.meta.env.VITE_SHOW_DEBUG !== "true") return null;

  return (
    <div className="debug-panel">
      <button type="button" onClick={() => setOpen((v) => !v)} className="debug-panel-toggle">
        {open ? "Скрыть debug" : "Показать debug"}
      </button>
      {open ? <pre className="debug-panel-body">{JSON.stringify(conversation, null, 2)}</pre> : null}
    </div>
  );
}
