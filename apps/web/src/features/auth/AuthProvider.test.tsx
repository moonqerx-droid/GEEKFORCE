import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { AuthProvider, useAuth } from "./AuthProvider";

function Probe() {
  const auth = useAuth();
  return <div>{auth.status}:{auth.user?.role ?? "none"}</div>;
}

describe("AuthProvider", () => {
  it("loads the current authenticated user", async () => {
    server.use(http.get("*/api/auth/me", () => HttpResponse.json({
      id: "1", first_name: "Анна", last_name: "Иванова", email: "a@example.ru",
      department: "it", role: "employee", email_verified_at: "2026-09-27T00:00:00Z",
    })));
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("authenticated:employee")).toBeInTheDocument();
  });

  it("treats 401 as anonymous", async () => {
    server.use(http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByText("anonymous:none")).toBeInTheDocument());
  });
});
