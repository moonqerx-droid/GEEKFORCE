import type { ConversationStatus, Department, StepOutcome, Urgency, UserRole } from "../api/types";

export const URGENCY_LABEL: Record<Urgency, string> = {
  low: "Не срочно",
  normal: "Обычная срочность",
  high: "Срочно",
  critical: "Критично",
};

export const URGENCY_SHORT: Record<Urgency, string> = {
  low: "Низкая",
  normal: "Обычная",
  high: "Высокая",
  critical: "Критическая",
};

export const URGENCY_TONE: Record<Urgency, "success" | "neutral" | "warning" | "danger"> = {
  low: "success",
  normal: "neutral",
  high: "warning",
  critical: "danger",
};

export const STATUS_LABEL: Record<ConversationStatus, string> = {
  NEW: "Новое",
  ANALYZING: "Разбираемся",
  CLARIFYING: "Уточняем детали",
  TROUBLESHOOTING: "Решаем по шагам",
  VERIFYING: "Проверяем результат",
  RESOLVED: "Решено",
  ESCALATED: "Ждёт специалиста",
  IN_PROGRESS: "Специалист в работе",
};

export const STATUS_TONE: Record<ConversationStatus, "neutral" | "accent" | "success" | "warning" | "human"> = {
  NEW: "neutral",
  ANALYZING: "accent",
  CLARIFYING: "accent",
  TROUBLESHOOTING: "accent",
  VERIFYING: "accent",
  RESOLVED: "success",
  ESCALATED: "warning",
  IN_PROGRESS: "human",
};

export const OUTCOME_LABEL: Record<StepOutcome, string> = {
  helped: "Помогло",
  not_helped: "Не помогло",
  cannot_perform: "Не получилось выполнить",
};

export const OUTCOME_TONE: Record<StepOutcome, "success" | "warning" | "danger"> = {
  helped: "success",
  not_helped: "warning",
  cannot_perform: "danger",
};

export const DEPARTMENT_LABEL: Record<Department, string> = {
  it: "IT",
  sales: "Продажи",
  marketing: "Маркетинг",
  finance: "Финансы",
  hr: "HR",
  operations: "Операционный отдел",
  other: "Другое",
};

/** Facts the engine extracts, named the way the employee would say it. */
export const FACT_LABEL: Record<string, string> = {
  affected_scope: "Кого затронуло",
  call_app: "Программа для звонков",
  colleagues_affected: "У коллег так же",
  entered_credentials: "Вводил пароль",
  error_text: "Что пишет система",
  had_access_before: "Доступ был раньше",
  headset: "Гарнитура",
  internet_works: "Интернет без VPN",
  location: "Где находится",
  mail_client: "Почтовая программа",
  other_device_works: "На другом устройстве работает",
  password_changed_recently: "Недавно менял пароль",
  resource: "Нужный ресурс",
  service_name: "Сервис",
  since_when: "С какого момента",
  vpn: "VPN",
  device: "Устройство",
  recurring: "Повторяется",
  critical_update: "Важное уточнение",
  problem_area: "Похоже на",
  details: "Подробности",
  also_reported: "Ещё сообщил",
  screenshot_text: "Текст на скриншоте",
};

const FACT_VALUE: Record<string, string> = {
  yes: "да",
  no: "нет",
  unknown: "не знает",
  laptop: "ноутбук",
  desktop: "компьютер",
  phone: "телефон",
  office: "в офисе",
  home: "дома",
  remote: "удалённо",
  wifi: "Wi-Fi",
  outlook: "Outlook",
  exchange: "Exchange",
  zoom: "Zoom",
  teams: "Teams",
  telemost: "Телемост",
  sip: "IP-телефония",
  chrome: "Chrome",
  excel: "Excel",
  word: "Word",
  jira: "Jira",
  confluence: "Confluence",
  bitrix: "Битрикс24",
  amocrm: "amoCRM",
  salesforce: "Salesforce",
  crm: "CRM",
  // Areas offered when the request is unclear (fact problem_area).
  password_login: "вход или пароль",
  email_outlook: "почта",
  vpn_connection: "VPN",
  network_wifi: "интернет или Wi-Fi",
  slow_performance: "медленная работа",
  access_rights: "доступ к папке или программе",
  other: "другое",
};

export const ROLE_LABEL: Record<UserRole, string> = {
  employee: "Сотрудник",
  operator: "Специалист поддержки",
  admin: "Руководитель поддержки",
};

export const ROLE_SHORT: Record<UserRole, string> = {
  employee: "Сотрудник",
  operator: "Специалист",
  admin: "Руководитель",
};

export const DEPARTMENTS = Object.keys(DEPARTMENT_LABEL) as Department[];

export function formatDateLong(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function formatRating(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(1).replace(".", ",");
}

export function formatPercent(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function factLabel(key: string): string {
  return FACT_LABEL[key] ?? key.replaceAll("_", " ");
}

export function factValue(value: string): string {
  return FACT_VALUE[value.toLowerCase()] ?? value;
}

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
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** "5 мин назад", "2 ч назад", "вчера" — for queues where recency matters more than the clock. */
export function formatAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return days === 1 ? "вчера" : `${days} дн назад`;
}

export function formatMinutes(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value < 0.5) return "меньше минуты";
  if (value < 60) return `${Math.round(value)} мин`;
  const hours = Math.floor(value / 60);
  const minutes = Math.round(value % 60);
  return minutes ? `${hours} ч ${minutes} мин` : `${hours} ч`;
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join("");
}

export function homePathFor(role: string): string {
  if (role === "admin") return "/admin";
  if (role === "operator") return "/operator";
  return "/employee";
}

/** Russian plural: plural(4, "сотрудник", "сотрудника", "сотрудников") → "сотрудника". */
export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
