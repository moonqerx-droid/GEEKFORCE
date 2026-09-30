/** A case scenario chosen on the login page travels to the employee's chat through the sign-in. */
const KEY = "helpflow.scenario";

export function rememberScenario(text: string) {
  try { window.sessionStorage.setItem(KEY, text); } catch { /* the jury then types it themselves */ }
}

/** The scenario to start with, once: reading it forgets it, so a reload does not repeat it. */
export function takeScenario(): string | null {
  try {
    const text = window.sessionStorage.getItem(KEY);
    if (text) window.sessionStorage.removeItem(KEY);
    return text;
  } catch {
    return null;
  }
}
