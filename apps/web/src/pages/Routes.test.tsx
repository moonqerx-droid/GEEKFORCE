import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Header } from "../components/Header";

describe("role-specific header", () => {
  it("shows no specialist switch in the employee cabinet", () => {
    render(<MemoryRouter><Header role="employee" name="Анна Иванова" onLogout={() => undefined} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Мои обращения" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Специалист" })).not.toBeInTheDocument();
  });

  it("shows queue navigation only for an operator", () => {
    render(<MemoryRouter><Header role="operator" name="Иван Петров" onLogout={() => undefined} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Обращения" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Мои обращения" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Пользователи" })).not.toBeInTheDocument();
  });

  it("gives the support lead the overview, the queue and the team", () => {
    render(<MemoryRouter><Header role="admin" name="Мария Иванова" onLogout={() => undefined} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Обзор" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Обращения" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Пользователи" })).toBeInTheDocument();
  });
});
