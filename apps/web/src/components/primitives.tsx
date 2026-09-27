import type { HTMLAttributes, ReactNode } from "react";
import { initials } from "../lib/labels";
import "./primitives.css";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={["card", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </div>
  );
}

type Tone = "neutral" | "success" | "warning" | "danger" | "accent" | "human";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label ?? "Загрузка…"}</span>
    </span>
  );
}

export function EmptyState({ title, description, children }: {
  title: string; description?: string; children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <p className="empty-state-title">{title}</p>
      {description ? <p className="empty-state-description">{description}</p> : null}
      {children}
    </div>
  );
}

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <p className="error-state-title">{title}</p>
      {description ? <p className="error-state-description">{description}</p> : null}
      {onRetry ? (
        <button type="button" className="error-state-retry" onClick={onRetry}>
          Повторить
        </button>
      ) : null}
    </div>
  );
}

/** The assistant's face: a coral speech mark. People get their initials on sea-green. */
export function Avatar({ kind, name, size = 32 }: {
  kind: "assistant" | "human" | "employee"; name?: string | null; size?: number;
}) {
  const style = { width: size, height: size, fontSize: Math.round(size * 0.38) };
  if (kind === "assistant") {
    return (
      <span className="avatar avatar-assistant" style={style} aria-hidden="true">
        <svg viewBox="0 0 24 24" width={size * 0.56} height={size * 0.56}>
          <path d="M5 5.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-7.2L7 20v-3.5H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z" fill="currentColor" />
          <circle cx="8.6" cy="11" r="1.25" fill="var(--coral)" />
          <circle cx="12" cy="11" r="1.25" fill="var(--coral)" />
          <circle cx="15.4" cy="11" r="1.25" fill="var(--coral)" />
        </svg>
      </span>
    );
  }
  return (
    <span className={`avatar avatar-${kind}`} style={style} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
