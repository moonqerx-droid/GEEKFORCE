import type { Conversation } from "../../api/types";
import type { StepMarker } from "./MessageThread";

/** Maps each step instruction the assistant sent to its number and result, so the thread can show it compactly. */
export function stepMarkers(conversation: Conversation | null): Map<string, StepMarker> {
  const markers = new Map<string, StepMarker>();
  if (!conversation) return markers;
  const done = [...conversation.completed_steps].sort((a, b) => a.position - b.position);
  done.forEach((step, index) => markers.set(step.instruction.trim(), { number: index + 1, outcome: step.outcome }));
  if (conversation.status === "TROUBLESHOOTING" && conversation.current_step) {
    markers.set(conversation.current_step.instruction.trim(), { number: done.length + 1, outcome: null });
  }
  return markers;
}
