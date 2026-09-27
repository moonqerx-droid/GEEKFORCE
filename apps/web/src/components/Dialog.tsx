import { useEffect, useId, useRef, type ReactNode } from "react";
import "./Dialog.css";

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog: focus moves inside, Tab stays inside, focus returns on close.
 * `onDismiss` enables Escape and the backdrop; leave it out for dialogs that must be
 * closed deliberately (a one-time password must not vanish on a stray key press).
 */
export function Dialog({
  title,
  children,
  onDismiss,
  role = "dialog",
  tone = "default",
  size = "md",
  placement = "center",
}: {
  placement?: "center" | "side";
  title: string;
  children: ReactNode;
  onDismiss?: () => void;
  role?: "dialog" | "alertdialog";
  tone?: "default" | "important";
  size?: "md" | "lg";
}) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const target = node?.querySelector<HTMLElement>("[data-autofocus]") ?? node?.querySelector<HTMLElement>(FOCUSABLE);
    target?.focus();
    return () => previous?.focus?.();
  }, []);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" && onDismiss) {
      event.stopPropagation();
      onDismiss();
      return;
    }
    if (event.key !== "Tab" || !ref.current) return;
    // A dialog opened inside another one owns its Tab cycle.
    event.stopPropagation();
    const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!items.length) return;
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className={`dialog-layer dialog-layer-${placement}`}>
      <div className="dialog-backdrop" aria-hidden="true" onClick={onDismiss} />
      <div
        ref={ref}
        className={`dialog dialog-${size} dialog-${tone} dialog-${placement}`}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className="dialog-title">{title}</h2>
        {children}
      </div>
    </div>
  );
}
