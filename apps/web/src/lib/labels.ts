import type { ConversationStatus, StepOutcome, Urgency } from "../api/types";

export const URGENCY_LABEL: Record<Urgency, string> = {
  low: "Низкая",
  normal: "Обычная",
  high: "Высокая",
  critical: "Критическая",
};

export const URGENCY_TONE: Record<Urgency, "success" | "accent" | "warning" | "danger"> = {
  low: "success",
  normal: "accent",
  high: "warning",
  critical: "danger",
};

export const STATUS_LABEL: Record<ConversationStatus, string> = {
  NEW: "Новое обращение",
  ANALYZING: "Анализируем обращение",
  CLARIFYING: "Уточняем детали",
  TROUBLESHOOTING: "Устраняем проблему",
  VERIFYING: "Проверяем результат",
  RESOLVED: "Решено",
  ESCALATED: "Передано специалисту",
};

export const OUTCOME_LABEL: Record<StepOutcome, string> = {
  helped: "Помогло",
  not_helped: "Не помогло",
  cannot_perform: "Не могу выполнить",
};

export const OUTCOME_TONE: Record<StepOutcome, "success" | "warning" | "danger"> = {
  helped: "success",
  not_helped: "warning",
  cannot_perform: "danger",
};

export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
