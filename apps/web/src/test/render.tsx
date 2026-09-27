import { render } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../api/types";
import { AuthProvider } from "../features/auth/AuthProvider";
import { server } from "./server";

export function makeUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: "user-1",
    first_name: "Иван",
    last_name: "Петров",
    email: "ivan@example.ru",
    department: "sales",
    role: "employee",
    email_verified_at: "2026-09-27T00:00:00Z",
    ...overrides,
  };
}

/** Renders a signed-in page the way the app does: router + auth context. */
export function renderAs(ui: ReactNode, user: AuthUser = makeUser(), path = "/") {
  server.use(http.get("*/api/auth/me", () => HttpResponse.json(user)));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}
