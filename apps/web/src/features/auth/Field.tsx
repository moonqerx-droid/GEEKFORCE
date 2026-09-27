import type { InputHTMLAttributes, ReactNode } from "react";

export function Field({ label, error, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & {
  label: string; error?: string; hint?: ReactNode;
}) {
  const id = props.id ?? props.name;
  const descriptionId = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return <label className="auth-field" htmlFor={id}>
    <span>{label}</span>
    <input {...props} id={id} aria-invalid={Boolean(error)} aria-describedby={descriptionId} />
    {error ? <small id={descriptionId} className="auth-field-error">{error}</small> :
      hint ? <small id={descriptionId}>{hint}</small> : null}
  </label>;
}
