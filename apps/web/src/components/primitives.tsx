import type { HTMLAttributes, ReactNode } from "react";
import "./primitives.css";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={["card", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </div>
  );
}

interface BadgeProps {
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
  children: ReactNode;
}

export function Badge({ tone = "neutral", children }: BadgeProps) {
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

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="empty-state">
      <p className="empty-state-title">{title}</p>
      {description ? <p className="empty-state-description">{description}</p> : null}
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
