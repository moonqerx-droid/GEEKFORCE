import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "./AuthProvider";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import App from "../../App";
import type { AuthUser } from "../../api/types";
import { makeProfile } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";

const temporary = makeUser({
  id: "u-petr", first_name: "Пётр", last_name: "Сидоров", role: "operator", must_change_password: true,
});

describe("forced password change", () => {
  it("sends a user with a temporary password to the change screen from any protected page", async () => {
    for (const path of ["/operator", "/profile", "/admin", "/employee"]) {
      const view = renderAs(<App />, temporary, path);
      expect(await screen.findByRole("heading", { name: "Задайте постоянный пароль" })).toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Разделы" })).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("lets the user out: logout stays available", async () => {
    let loggedOut = false;
    server.use(http.post("*/api/auth/logout", () => { loggedOut = true; return new HttpResponse(null, { status: 204 }); }));
    const user = userEvent.setup();
    renderAs(<App />, temporary, "/operator");

    await user.click(await screen.findByRole("button", { name: "Выйти" }));
    await waitFor(() => expect(loggedOut).toBe(true));
    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
  });

  it("changes the password, refreshes the session and opens the workspace", async () => {
    let current: AuthUser = temporary;
    let body: unknown;
    server.use(
      http.get("*/api/auth/me", () => HttpResponse.json(current)),
      http.post("*/api/auth/change-password", async ({ request }) => {
        body = await request.json();
        current = { ...temporary, must_change_password: false };
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/api/operator/tickets", () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderAs(<App />, temporary, "/operator");
    server.use(http.get("*/api/auth/me", () => HttpResponse.json(current)));

    const form = await screen.findByRole("form", { name: "Постоянный пароль" });
    await user.type(within(form).getByLabelText("Временный пароль"), "Tmp-9xQ4-LmZ2");
    await user.type(within(form).getByLabelText("Новый пароль"), "MyStrong2026");
    await user.type(within(form).getByLabelText("Повторите новый пароль"), "MyStrong2026");
    await user.click(within(form).getByRole("button", { name: "Сохранить пароль" }));

    expect(await screen.findByText("Очередь пуста")).toBeInTheDocument();
    expect(body).toEqual({ current_password: "Tmp-9xQ4-LmZ2", password: "MyStrong2026", password_confirmation: "MyStrong2026" });
  });

  it("does not loop: without a pending change the screen sends the user home", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([])));
    renderAs(<App />, makeUser({ role: "operator" }), "/change-password");
    expect(await screen.findByText("Очередь пуста")).toBeInTheDocument();
  });
});

describe("route protection", () => {
  it("keeps employees out of the admin area and specialists out of the team page", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([])));
    const employeeView = renderAs(<App />, makeUser(), "/admin/team");
    expect(await screen.findByRole("heading", { name: "Что случилось?" })).toBeInTheDocument();
    employeeView.unmount();

    renderAs(<App />, makeUser({ role: "operator" }), "/admin/team");
    expect(await screen.findByText("Очередь пуста")).toBeInTheDocument();
  });

  it("sends a signed-out visitor to sign in", async () => {
    server.use(http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })));
    render(<MemoryRouter initialEntries={["/profile"]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
  });

  it("opens the profile from the header for every role", async () => {
    server.use(http.get("*/api/profile", () => HttpResponse.json(makeProfile({ role: "operator", name: "Анна Смирнова" }))));
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([])));
    const user = userEvent.setup();
    renderAs(<App />, makeUser({ role: "operator", first_name: "Анна", last_name: "Смирнова" }), "/operator");

    await user.click(await screen.findByRole("link", { name: /Профиль/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Анна Смирнова" })).toBeInTheDocument();
  });

  it("no longer offers invite-based specialist sign-up in navigation", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([])));
    renderAs(<App />, makeUser({ role: "admin" }), "/admin/team");
    server.use(http.get("*/api/admin/users", () => HttpResponse.json([])));
    await screen.findByRole("navigation", { name: "Разделы" });
    expect(screen.queryByRole("link", { name: /приглаш/i })).not.toBeInTheDocument();
  });
});
